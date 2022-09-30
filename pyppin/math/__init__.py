"""Mathematical utilities."""
from typing import Iterable, Tuple


def round_up_to(value: float, multiple_of: float) -> float:
    """Round ``value`` up to the nearest multiple of ``multiple_of``."""
    float_count = value / multiple_of
    int_count = int(float_count)
    if float_count != int_count:
        int_count += 1
    return multiple_of * int_count


def cap(value: float, min: float, max: float) -> float:
    """Cap a value to an interval."""
    return min if value <= min else max if value >= max else value


def within(value: float, min: float, max: float) -> bool:
    """Test if value is in [min, max)."""
    return value >= min and value < max


def minmax(data: Iterable[float]) -> Tuple[float, float]:
    """Return (min, max) of data in one pass."""
    low = float("inf")
    hi = -float("inf")
    for value in data:
        low = min(low, value)
        hi = max(hi, value)
    return low, hi
