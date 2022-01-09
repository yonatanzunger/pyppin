import unittest
from pyppin.math.plot_ascii import plot_ascii, Axis


class PlotAsciiTest(unittest.TestCase):
    def testPlotFunction(self) -> None:
        print(
            plot_ascii(
                lambda x: (x - 1) ** 3 + 1,
                width=100,
                height=50,
                x_axis=Axis(min=0, max=2),
                vfill=True,
            )
        )
        assert False
