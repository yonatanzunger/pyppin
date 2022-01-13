"""Mathematical utilities."""


def round_up_to(value: float, multiple_of: float) -> float:
    """Round <value> up to the nearest multiple of <float>."""
    float_count = value / multiple_of
    int_count = int(float_count)
    if float_count != int_count:
        int_count += 1
    return multiple_of * int_count


def cap(value: float, min: float, max: float) -> float:
    if value <= min:
        return min
    elif value >= max:
        return max
    else:
        return value
