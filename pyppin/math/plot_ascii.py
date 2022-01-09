import array
import bisect
import io
from typing import Callable, Dict, List, NamedTuple, Optional, Tuple, Union

from pyppin.base import assert_not_none


class Interpolate(object):
    """Use this to turn a list or dict of (x, y) tuples into a function."""

    def __init__(
        self, data: Union[List[Tuple[float, float]], Dict[float, float]]
    ) -> None:
        if isinstance(data, dict):
            self.data = sorted(list(data.items()))
        else:
            self.data = sorted(data)

        if self.data:
            self.xmin = self.data[0][0]
            self.xmax = self.data[-1][0]
            self.ymax = self.ymin = self.data[0][1]
            prev_x = self.xmin
            for point in self.data[1:]:
                if prev_x == point[0]:
                    raise ValueError(
                        f"Multiple values provided for x={prev_x}; cannot interpolate."
                    )
                prev_x = point[0]
                self.ymin = min(self.ymin, point[1])
                self.ymax = max(self.ymax, point[1])
        else:
            self.xmin = self.xmax = self.ymin = self.ymax = 0.0

    def __call__(self, arg: float) -> float:
        """Evaluate using linear interpolation."""
        if arg < self.xmin or arg > self.xmax:
            raise ValueError(f"Argument {arg} out of range [{self.xmin}, {self.xmax}]")
        # The index of the first entry with x > arg.
        gt_index = bisect.bisect_right(self.data, (arg, 0))
        # This *should* be guaranteed by the range check!
        assert gt_index > 0 and gt_index < len(self.data)
        left = self.data[gt_index - 1]
        right = self.data[gt_index]

        position = (arg - left[0]) / (right[0] - left[0])
        return left[1] + position * (right[1] - left[1])


class Axis(NamedTuple):
    """Information about an axis of the plot"""

    min: Optional[float] = None
    """The minimum value to show on the plot, or None to infer from data."""
    max: Optional[float] = None
    """The maximum value to show on the plot, or None to infer from data."""
    labels: Optional[Dict[float, str]] = None
    """Axis labels, or None to infer from data."""


def plot_ascii(
    data: Callable[[float], float],
    width: int,
    height: int,
    x_axis: Optional[Axis] = None,
    y_axis: Optional[Axis] = None,
    vfill: bool = False,
) -> str:
    """Create an ASCII-art plot of some numerical data.

    Args:
        data: The data to be plotted. If you have a list or a dict, use an Interpolate to
            turn it into a function.
        width, height: The size, in characters, of the output to generate.
        x_axis, y_axis: Options for the axes.
        vfill: If True, show a vertical fill (in the style of a bar chart) below each value.
            If False, show the values as points.

    Returns:
        Beautiful ASCII art.
    """
    return _PlotInfo(data, width, height, x_axis or Axis(), y_axis or Axis()).plot(
        vfill
    )


#################################################################################################
# Implementation details
#
# We work in three coordinate systems:
# - Natural coordinates (float) are the X and Y values of the function itself, with the origin
#   at the lower left.
# - Image coordinates (int) are pixel positions relative to the image region of the output, i.e.
#   the sub-box inside the axes, with the origin at the lower left.
# - Screen coordinates (int) are pixel positions within the full width ⊗ height grid, with the
#   origin at the upper left.


class _PlotInfo(object):
    def __init__(
        self,
        data: Callable[[float], float],
        width: int,
        height: int,
        x_axis: Axis,
        y_axis: Axis,
    ) -> None:
        self.data = data
        self.width = width
        self.height = height
        self.xmin, self.xmax, self.ymin, self.ymax = _get_range(
            data, width, height, x_axis, y_axis
        )

        print(f"X [{self.xmin}, {self.xmax}) Y [{self.ymin}, {self.ymax})")

        # Now we need to figure out the labels, which we'll use to compute the dimensions of the
        # image area (i.e., the total area minus the axes) The X-labels are easy: if we have them at
        # all (i.e., unless x_axis.labels was explicitly an empty dict) they take up one vertical
        # pixel, and the axis itself takes up one.
        has_x_labels = x_axis.labels is None or x_axis.labels
        self.x_axis_height = 2 if has_x_labels else 1
        self.image_height = height - self.x_axis_height
        if self.image_height < 1:
            raise ValueError("No visual room to produce the image: height is too small")

        # We now know our y-axis scale, and can call the Y-axis coordinate functions!
        self.yscale = (self.image_height - 1) / (self.ymax - self.ymin)

        # Using this, we can build out the set of Y-axis labels. This will be a map from screen
        # Y coordinate to label text.
        if y_axis.labels is not None:
            self.y_labels = {
                self.natural_to_screen_y(position): label
                for position, label in y_axis.labels.items()
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

        print(self.y_labels)

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
        if x_axis.labels is not None:
            self.x_labels = {
                self.natural_to_image_x(position): label
                for position, label in x_axis.labels.items()
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
        return self.image_to_screen_x(self.natural_to_screen_x(arg))

    def natural_to_screen_y(self, arg: float) -> int:
        """Convert natural coordinates to screen coordinates on the Y axis."""
        return self.image_to_screen_y(self.natural_to_image_y(arg))

    def image_to_index(self, x: int, y: int) -> int:
        """Convert image coordinates into a bitmap array index."""
        return y * self.image_width + x

    def image_row(self, image: array.array, y: int) -> str:
        """Fetch a row of a bitmap."""
        start = self.image_to_index(0, y)
        return image[start : start + self.image_width].tobytes().decode("ascii")

    def plot(self, vfill: bool) -> str:
        # Compute the output image grid. (Yes, we *could* do this in the opposite order and do
        # everything in one pass, but it's a real PITA and not worth it.)
        image = array.array("b", b" " * self.image_width * self.image_height)

        for image_x in range(self.image_width):
            image_y = self.natural_to_image_y(
                self.data(self.image_to_natural_x(image_x))
            )
            # 35 is a hash mark.
            if vfill:
                for y in range(image_y):
                    image[self.image_to_index(image_x, y)] = 35
            else:
                image[self.image_to_index(image_x, image_y)] = 35

        # And now, let's generate our final output.
        output = io.StringIO()

        for yscreen in range(self.height):
            if yscreen < self.image_height:
                # Draw the Y-axis, including its labels.
                if yscreen in self.y_labels:
                    output.write(self.y_labels[yscreen])
                    output.write(" +")
                else:
                    output.write(self.y_axis_padding)
                    output.write("|")

                # And now draw the row of the image.
                output.write(self.image_row(image, self.screen_to_image_y(yscreen)))

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


def _get_range(
    data: Callable[[float], float], width: int, height: int, x_axis: Axis, y_axis: Axis
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
        if not isinstance(data, Interpolate):
            raise ValueError(
                "No range was given for the X-axis, and it cannot be derived from the data. "
                "Please specify explicit values."
            )
        xmin = xmin if xmin is not None else data.xmin
        xmax = xmax if xmax is not None else data.xmax

    # Now let's get the true Y range. We prefer the stuff from the options. If we don't have that
    # and this is interpolated data, fetch from there.
    if (ymin is None or ymax is None) and isinstance(data, Interpolate):
        ymin = ymin if ymin is not None else data.ymin
        ymax = ymax if ymax is not None else data.ymax

    # If we still don't have some of the Y-values, we'll have to do a quick evaluation. We don't
    # know exactly how many X pixels we'll have yet, so we'll do it at fairly high resolution to
    # maximize the chance of spotting local maxima.
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
