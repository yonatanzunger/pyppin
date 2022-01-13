import bisect
from typing import Dict, List, Tuple, Union


class FunctionFromSortedData(object):
    """Base class for a bunch of Callable[[float], float] that are based on sorted (x, y) inputs
    at fixed data points.
    """

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
        raise NotImplementedError()

    def _left_of(self, arg: float) -> int:
        """Return the index in self.data of the greatest item <= arg."""
        gt_index = bisect.bisect_right(self.data, (arg, 0))
        # An index of zero is OK in only this case.
        if not gt_index and self.data[0][0] == arg:
            return 0
        elif not gt_index or gt_index >= len(self.data):
            raise ValueError(f"Argument {arg} out of range [{self.xmin}, {self.xmax}]")
        return gt_index - 1


class Interpolate(FunctionFromSortedData):
    """A function that linearly interpolates between a sequence of values.

    This is useful if you want to plot or otherwise process a set of numbers.
    """

    def __call__(self, arg: float) -> float:
        """Evaluate using linear interpolation."""
        left_index = self._left_of(arg)
        left = self.data[left_index]
        right = self.data[left_index + 1]
        position = (arg - left[0]) / (right[0] - left[0])
        return left[1] + position * (right[1] - left[1])


class PiecewiseConstant(FunctionFromSortedData):
    """A piecewise-constant function."""

    def __call__(self, arg: float) -> float:
        left_index = self._left_of(arg)
        return self.data[left_index][1]
