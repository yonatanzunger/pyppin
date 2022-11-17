"""Generate ASCII-art plots of functions and data."""

import array
import io
from typing import Callable, Dict, List, NamedTuple, Optional, Tuple

from pyppin.base import assert_not_none
from pyppin.math import cap
from pyppin.math.functions import FunctionFromSortedData


def plot_ascii(
    data: Callable[[float], float],
    width: int = 100,
    height: int = 0,
    x_axis: Optional["AxisOptions"] = None,
    y_axis: Optional["AxisOptions"] = None,
    vfill: bool = False,
    plot_symbol: str = "#",
) -> str:
    """Create an ASCII-art plot of some numerical data.

    Args:
        data: The data to be plotted. If you want to plot a list or dict of data, rather than
            a function, use the helpers in pyppin.math.functions to convert them.
        width, height: The size, in characters, of the output to generate. The height will
            default to half the width.
        x_axis, y_axis: Options for the axes.
        vfill: If True, show a vertical fill (in the style of a bar chart) below each value.
            If False, show the values as points.
        plot_symbol: The char to use when plotting it.

    Returns:
        Beautiful ASCII art, like this::

             >>> print(plot_ascii(math.cos, width=80, x_axis=AxisOptions(min=0, max=10), y_axis=AxisOptions(min=-1.5, max=1.5)))
             1.5 +
                 |
                 |
                 |
                 |
             1.1 +
                 |
                 |###                                         #####
                 |   ##                                     ##     #
                 |     #                                   #        #
             0.7 +                                        #          #
                 |      #                                             #
                 |       #                               #             #
                 |        #                             #
                 |                                                      #
             0.3 +         #                           #                 #
                 |                                    #
                 |          #                                             #
                 |           #                       #                     #
                 |
            -0.1 +            #                     #                       #
                 |                                 #
                 |             #                                             #
                 |              #                 #                           #
                 |
            -0.5 +               #               #                             #
                 |                #             #                               #
                 |                 #           #
                 |                            #                                  #
                 |                  #        #                                    #        #
            -0.9 +                   ##     #                                      ##     #
                 |                     #####                                         #####
                 |
                 |
                 |
            -1.3 +
                 |
                 |
                 ++----+----+----+----+----+----+----+----+----+----+----+----+----+----+---
                  0.0  0.7  1.4  2.1  2.7  3.4  4.1  4.8  5.5  6.2  6.8  7.5  8.2  8.9  9.6
    """
    height = height or width // 2
    canvas = Canvas.for_plot(
        data, width=width, height=height, x_axis=x_axis, y_axis=y_axis
    )
    canvas.plot(data, vfill=vfill, symbol=plot_symbol)
    return canvas.render()


class AxisOptions(NamedTuple):
    """Information about an axis of the plot"""

    min: Optional[float] = None
    """The minimum value to show on the plot, or None to infer from data."""
    max: Optional[float] = None
    """The maximum value to show on the plot, or None to infer from data."""
    labels: Optional[Dict[float, str]] = None
    """Axis labels, or None to infer from data."""


class Canvas(object):
    """A Canvas is an object for drawing ASCII plots.

    It works in terms of three coordinate systems:
    - Natural coordinates (float) are the X and Y values of the function itself, with the origin
      at the lower left.
    - Image coordinates (int) are pixel positions relative to the image region of the output, i.e.
      the sub-box inside the axes, with the origin at the lower left.
    - Screen coordinates (int) are pixel positions within the full width ⊗ height grid, with the
      origin at the upper left.

    Args:
        width, height: The dimensions in pixels (ie chars) of the output image.
        x_range, y_range: The X and Y axis ranges, in natural coordinates.
        x_labels, y_labels: Optional dicts from natural coordinate to label for the axes.
        background: The background symbol for the plot.

    If the labels aren't given, they will be inferred. If you want no labels, pass an explicit empty
    dict.
    """

    def __init__(
        self,
        width: int,
        height: int,
        x_range: Tuple[float, float],
        y_range: Tuple[float, float],
        x_labels: Optional[Dict[float, str]] = None,
        y_labels: Optional[Dict[float, str]] = None,
        background: str = " ",
    ) -> None:
        self.width = width
        self.height = height
        self.xmin, self.xmax = x_range
        self.ymin, self.ymax = y_range

        assert self.xmin < self.xmax
        assert self.ymin < self.ymax
        assert len(background) == 1

        # Now we need to figure out the labels, which we'll use to compute the dimensions of the
        # image area (i.e., the total area minus the axes) The X-labels are easy: if we have them at
        # all (i.e., unless x_axis.labels was explicitly an empty dict) they take up one vertical
        # pixel, and the axis itself takes up one.
        has_x_labels = x_labels is None or x_labels
        self.x_axis_height = 2 if has_x_labels else 1
        self.image_height = height - self.x_axis_height
        if self.image_height < 1:
            raise ValueError("No visual room to produce the image: height is too small")

        # We now know our y-axis scale, and can call the Y-axis coordinate functions!
        self.yscale = (self.image_height - 1) / (self.ymax - self.ymin)

        # Using this, we can build out the set of Y-axis labels. This will be a map from screen
        # Y coordinate to label text.
        if y_labels is not None:
            self.y_labels = {
                self.natural_to_screen_y(position): label
                for position, label in y_labels.items()
                if position >= self.ymin and position <= self.ymax
            }
        else:
            # Let's try to stick in one Y label every 5 pixels. Always stick a label at the max
            # value.
            labeler = _LabelMaker(self.ymin, self.ymax)
            self.y_labels = {
                self.image_to_screen_y(position): labeler(
                    self.image_to_natural_y(position)
                )
                for position in range(self.image_height - 1, -1, -5)
            }

        # The display width of the Y-axis labels, including the spacing char if required.
        y_label_width = (
            (1 + max(len(label) for label in self.y_labels.values()))
            if self.y_labels
            else 0
        )
        # This is the padding we're going to show on rows where there isn't a Y label.
        self.y_axis_padding = " " * y_label_width
        self.y_axis_width = y_label_width + 1
        self.image_width = width - self.y_axis_width
        if self.image_width < 1:
            raise ValueError(
                f"No visual room to produce the image: width is {width} but the y-axis "
                f"requires {self.y_axis_width} pixels."
            )

        # And now we know our X scale factor, and can convert X coordinates as well!
        self.xscale = (self.image_width - 1) / (self.xmax - self.xmin)

        # With the image width in hand, we can compute the X axis labels. Here we'd like to stick
        # two spaces between the narrowest gap between X values, so we're going to have to iterate a
        # bit.
        # Unlike y_labels, this will be a map from *image* X to value.
        if x_labels is not None:
            self.x_labels = {
                self.natural_to_image_x(position): label
                for position, label in x_labels.items()
                if position >= self.xmin and position <= self.xmax
            }
        else:
            # Start with a guess and iterate.
            labeler = _LabelMaker(self.xmin, self.xmax)
            widest_x_label = 5
            while True:
                self.x_labels = {
                    image_x: labeler(self.image_to_natural_x(image_x))
                    for image_x in range(0, self.image_width, widest_x_label + 2)
                }
                if not self.x_labels:
                    break
                true_widest_label = max(len(label) for label in self.x_labels.values())
                if true_widest_label == widest_x_label:
                    break
                widest_x_label = true_widest_label

        # And finally, we can create the bitmap object for our image region.
        self.image = array.array("u", background * self.image_width * self.image_height)

    @classmethod
    def for_plot(
        self,
        data: Callable[[float], float],
        width: int,
        height: int,
        x_axis: Optional[AxisOptions] = None,
        y_axis: Optional[AxisOptions] = None,
        background: str = " ",
    ) -> "Canvas":
        """Create a Canvas suited to displaying this plot on its own.

        Args:
            data: The function you are going to plot.
            width, height: The dimensions of the output canvas.
            x_axis, y_axis: Per-axis options.
            background: The background char for the plot.
        """
        x_axis = x_axis or AxisOptions()
        y_axis = y_axis or AxisOptions()
        xmin, xmax, ymin, ymax = _get_range(data, width, height, x_axis, y_axis)
        return Canvas(
            width=width,
            height=height,
            x_range=(xmin, xmax),
            y_range=(ymin, ymax),
            x_labels=x_axis.labels,
            y_labels=y_axis.labels,
            background=background,
        )

    def natural_to_image_x(self, arg: float) -> int:
        """Convert natural coordinates to image coordinates on the X axis."""
        assert arg >= self.xmin
        assert arg <= self.xmax
        return int(self.xscale * (arg - self.xmin))

    def natural_to_image_y(self, arg: float) -> int:
        """Convert natural coordinates to image coordinates on the Y axis."""
        assert arg >= self.ymin
        assert arg <= self.ymax
        return int(self.yscale * (arg - self.ymin))

    def image_to_natural_x(self, arg: int) -> float:
        """Convert image to natural coordinates on the X axis."""
        assert arg >= 0
        assert arg < self.image_width
        return self.xmin + (arg / self.xscale)

    def image_to_natural_y(self, arg: int) -> float:
        """Convert image to natural coordinates on the Y axis."""
        assert arg >= 0
        assert arg < self.image_height
        return self.ymin + (arg / self.yscale)

    def image_to_screen_x(self, arg: int) -> int:
        """Convert image to screen coordinates on the X axis."""
        assert arg >= 0
        assert arg < self.image_width
        return arg + self.y_axis_width

    def image_to_screen_y(self, arg: int) -> int:
        """Convert image to screen coordinates on the Y axis."""
        assert arg >= 0
        assert arg < self.image_height
        return self.image_height - 1 - arg

    def screen_to_image_x(self, arg: int) -> int:
        """Convert screen to image coordinates on the X axis."""
        assert arg >= 0
        assert arg < self.width
        return arg - self.y_axis_width

    def screen_to_image_y(self, arg: int) -> int:
        """Convert screen to image coordinates on the Y axis."""
        assert arg >= 0
        assert arg < self.height
        return self.image_height - 1 - arg

    def natural_to_screen_x(self, arg: float) -> int:
        """Convert natural coordinates to screen coordinates on the X axis."""
        return self.image_to_screen_x(self.natural_to_image_x(arg))

    def natural_to_screen_y(self, arg: float) -> int:
        """Convert natural coordinates to screen coordinates on the Y axis."""
        return self.image_to_screen_y(self.natural_to_image_y(arg))

    def pixel(self, image_x: int, image_y: int) -> str:
        return self.image[self._image_to_index(image_x, image_y)]

    def set_pixel(self, image_x: int, image_y: int, char: str) -> None:
        assert len(char) == 1
        self.image[self._image_to_index(image_x, image_y)] = char

    def plot(self, data: Callable[[float], float], vfill: bool, symbol: str) -> None:
        """Add a function plot on top of the canvas.

        Args:
            data: The function to plot.
            vfill: If true, add vertical "fill" lines (like in a bar graph) below the
                curve.
            symbol: The character to use for the plot line.
        """
        if len(symbol) != 1:
            raise ValueError(
                f'"{symbol}" is not a valid plot symbol; it needs to be one char.'
            )

        for image_x in range(self.image_width):
            try:
                natural_y = data(self.image_to_natural_x(image_x))
            except ValueError:
                continue
            # Values that go off the grid
            if natural_y < self.ymin:
                continue
            if natural_y > self.ymax and not vfill:
                continue
            image_y = self.natural_to_image_y(cap(natural_y, self.ymin, self.ymax))
            if vfill:
                for y in range(image_y):
                    self.image[self._image_to_index(image_x, y)] = symbol
            else:
                self.image[self._image_to_index(image_x, image_y)] = symbol

    def scatter_plot(self, data: List[Tuple[float, float]], symbol: str) -> None:
        """Add a scatter plot of (x, y) pairs."""
        if len(symbol) != 1:
            raise ValueError(
                f'"{symbol}" is not a valid plot symbol; it needs to be one char.'
            )

        for x, y in data:
            self.image[
                self._image_to_index(
                    self.natural_to_image_x(x), self.natural_to_image_y(y)
                )
            ] = symbol

    def render(self) -> str:
        """Actually generate the output plot."""
        output = io.StringIO()

        for yscreen in range(self.height):
            if yscreen < self.image_height:
                # Draw the Y-axis, including its labels.
                if yscreen in self.y_labels:
                    output.write(self.y_labels[yscreen].rjust(self.y_axis_width - 2))
                    output.write(" +")
                else:
                    output.write(self.y_axis_padding)
                    output.write("|")

                # And now draw the row of the image.
                output.write(self._image_row(self.screen_to_image_y(yscreen)))

            elif yscreen == self.image_height:
                # Draw the X axis itself.
                output.write(self.y_axis_padding)
                output.write("+")
                for image_x in range(self.image_width):
                    output.write("+" if image_x in self.x_labels else "-")

            elif yscreen == self.image_height + 1:
                # Draw the X-axis labels.
                output.write(self.y_axis_padding)
                output.write(" ")
                image_x = 0
                while image_x < self.image_width:
                    if image_x in self.x_labels:
                        output.write(self.x_labels[image_x])
                        output.write("  ")
                        image_x += len(self.x_labels[image_x]) + 2
                    else:
                        output.write(" ")
                        image_x += 1

            output.write("\n")

        return output.getvalue()

    def _image_to_index(self, x: int, y: int) -> int:
        """Convert image coordinates into a bitmap array index."""
        return y * self.image_width + x

    def _image_row(self, y: int) -> str:
        """Fetch a row of a bitmap."""
        start = self._image_to_index(0, y)
        return self.image[start : start + self.image_width].tounicode()


def _get_range(
    data: Optional[Callable[[float], float]],
    width: int,
    height: int,
    x_axis: AxisOptions,
    y_axis: AxisOptions,
) -> Tuple[float, float, float, float]:
    """Compute the X and Y ranges to plot.

    Returns xmin, xmax, ymin, ymax.
    """
    xmin = x_axis.min
    xmax = x_axis.max
    ymin = y_axis.min
    ymax = y_axis.max

    # First, let's get the true X range that we want.
    if xmin is None or xmax is None:
        if not isinstance(data, FunctionFromSortedData):
            raise ValueError(
                "No range was given for the X-axis, and it cannot be derived from the data. "
                "Please specify explicit values."
            )
        xmin = xmin if xmin is not None else data.xmin
        xmax = xmax if xmax is not None else data.xmax

    # Now let's get the true Y range. We prefer the stuff from the options. If we don't have that
    # and this is interpolated data, fetch from there.
    if (ymin is None or ymax is None) and isinstance(data, FunctionFromSortedData):
        ymin = ymin if ymin is not None else data.ymin
        ymax = ymax if ymax is not None else data.ymax

    # If we still don't have some of the Y-values, we'll have to do a quick evaluation. We don't
    # know exactly how many X pixels we'll have yet, so we'll do it at fairly high resolution to
    # maximize the chance of spotting local maxima.
    if ymin is None or ymax is None:
        if data is None:
            raise ValueError(
                "No range was given for the Y-axis, and it cannot be derived from the data. "
                "Please specify explicit values."
            )
        est_ymin, est_ymax = _estimated_yrange(data, xmin, xmax, max(width, 500))
        ymin = ymin if ymin is not None else est_ymin
        ymax = ymax if ymax is not None else est_ymax

    return (
        assert_not_none(xmin),
        assert_not_none(xmax),
        assert_not_none(ymin),
        assert_not_none(ymax),
    )


def _estimated_yrange(
    data: Callable[[float], float], xmin: float, xmax: float, steps: int
) -> Tuple[float, float]:
    """Estimate ymin and ymax."""
    ymin = ymax = data(xmin)
    for i in range(steps):
        x = xmin + (i + 1) * (xmax - xmin) / steps
        value = data(x)
        ymin = min(ymin, value)
        ymax = max(ymin, value)
    return ymin, ymax


class _LabelMaker(object):
    def __init__(self, min: float, max: float) -> None:
        self.min = min
        self.max = max

    def __call__(self, arg: float) -> str:
        # TODO make a better function for this!
        return f"{arg:0.1f}"
