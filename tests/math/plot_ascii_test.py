import unittest

from pyppin.math.plot_ascii import AxisOptions, Canvas, plot_ascii


class PlotAsciiTest(unittest.TestCase):
    def testCanvasCoords(self) -> None:
        canvas = Canvas(
            width=20,
            height=10,
            x_range=(1, 7),
            y_range=(-5, 5),
            background=".",
        )
        self.assertEqual(20, canvas.width)
        self.assertEqual(10, canvas.height)
        self.assertEqual(1, canvas.xmin)
        self.assertEqual(7, canvas.xmax)
        self.assertEqual(-5, canvas.ymin)
        self.assertEqual(5, canvas.ymax)

        self.assertEqual(2, canvas.x_axis_height)
        self.assertEqual(canvas.height - canvas.x_axis_height, canvas.image_height)
        self.assertEqual(
            (canvas.image_height - 1) / (canvas.ymax - canvas.ymin), canvas.yscale
        )

        self.assertEqual(canvas.width - canvas.y_axis_width, canvas.image_width)
        self.assertEqual(
            (canvas.image_width - 1) / (canvas.xmax - canvas.xmin), canvas.xscale
        )

        self.assertEqual(0, canvas.natural_to_image_x(canvas.xmin))
        self.assertEqual(canvas.image_width - 1, canvas.natural_to_image_x(canvas.xmax))
        self.assertEqual(0, canvas.natural_to_image_y(canvas.ymin))
        self.assertEqual(
            canvas.image_height - 1, canvas.natural_to_image_y(canvas.ymax)
        )

        self.assertEqual(canvas.y_axis_width, canvas.natural_to_screen_x(canvas.xmin))
        self.assertEqual(canvas.width - 1, canvas.natural_to_screen_x(canvas.xmax))
        self.assertEqual(
            canvas.image_height - 1, canvas.natural_to_screen_y(canvas.ymin)
        )
        self.assertEqual(0, canvas.natural_to_screen_y(canvas.ymax))

        self.assertEqual(canvas.xmin, canvas.image_to_natural_x(0))
        self.assertEqual(canvas.xmax, canvas.image_to_natural_x(canvas.image_width - 1))
        self.assertEqual(canvas.ymin, canvas.image_to_natural_y(0))
        self.assertEqual(
            canvas.ymax, canvas.image_to_natural_y(canvas.image_height - 1)
        )

        self.assertEqual(".", canvas.pixel(5, 5))
        canvas.set_pixel(5, 5, "#")
        canvas.set_pixel(10, 5, "X")
        self.assertEqual("#", canvas.pixel(5, 5))
        self.assertEqual(
            5 * "." + "#" + 4 * "." + "X" + (canvas.image_width - 11) * ".",
            canvas._image_row(5),
        )

        # Draw a horizontal line and see that it fills up a row.
        image_row = canvas.natural_to_image_y(2)
        natural_y = canvas.image_to_natural_y(image_row)
        canvas.plot(lambda x: natural_y, vfill=False, symbol="@")
        self.assertEqual("@" * canvas.image_width, canvas._image_row(image_row))

        self.assertEqual(
            " 5.0 +..............\n"
            "     |..............\n"
            "     |.....#....X...\n"
            "     |@@@@@@@@@@@@@@\n"
            "     |..............\n"
            "-2.1 +..............\n"
            "     |..............\n"
            "     |..............\n"
            "     ++----+----+---\n"
            "      1.0  3.3  5.6  \n",
            canvas.render(),
        )

    def testPlotFunction(self) -> None:
        plot_ascii(
            lambda x: (x - 1) ** 3 + 1,
            width=100,
            height=50,
            x_axis=AxisOptions(min=0, max=2),
            vfill=True,
        )
