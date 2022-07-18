import math
from enum import Enum
from typing import Union


class Mode(Enum):
    DECIMAL = 0
    BINARY = 1
    IEC = 2


def si_prefix(
    value: Union[float, int],
    mode: Mode = Mode.DECIMAL,
    threshold: float = 1.1,
    precision: int = 1,
    ascii_only: bool = False,
    sign: bool = False,
) -> str:
    """Format a number as a string, using SI (système internationale) prefixes. For example,
    turn 1,234,567 into 1.2M.

    Args:
        value: The number to be formatted.
        mode: Whether to use decimal or binary SI units. (See below for more info)
            Decimal: 1k = 1000
            Binary: 1k = 1024, but use the ordinary symbols k, M, etc.
            IEC: 1k = 1024, but write ki, Mi, etc., as per the IEC80000 standard.
        threshold: How far above the minimum for a prefix to go before using it. For example,
            if the threshold is set to 1.1 and we're in decimal mode, then 1050 will still be
            written as 1050, but 1100 will be written as 1.1k; likewise, 1050000 will be 1050k,
            and 1100000 will be 1.1M.
        precision: The number of digits after the decimal point to show.
        ascii_only: If False, then "micro" will be denoted with μ, as per the standard. If True,
            we use the ASCII letter u instead; this is important for some legacy environments
            that can't support Unicode.
        sign: If True, then we will prepend a + sign for positive numbers.

    Returns:
        A string formatting the indicated number, with a following optional suffix.
    """
    assert threshold != 0
    assert precision >= 0

    # Special cases
    if value == 0:
        return "0"
    elif not math.isfinite(value):
        if sign and value > 0:
            return '+' + str(value)
        else:
            return str(value)

    # Normalize signs
    if value < 0:
        sign = '-'
        value = -value
    else:
        sign = '+' if sign else ''

    base = 1000 if mode == Mode.DECIMAL else 1024
    # log_value == log base 1k of the value.
    log_value = math.log(value, base)
    # The index is which element of which array we'll use. (Negative values for the _NEGATIVE
    # arrays, positive ones for the _POSITIVE array; note that 1 is the base value for each array,
    # but only after we're done adjusting the index!)
    index = math.floor(log_value)
    delta = log_value - index
    log_threshold = math.log(threshold, base)

    # Now apply the threshold. Shift points from index into delta until delta is bigger than
    # log_threshold.
    if delta < log_threshold:
        index = index - 1
        delta = delta + 1

    # If index is zero, then we have no suffix at all!
    if index == 0:
        if isinstance(value, int):
            return sign + str(value)
        else:
            format_string = f'%0.{precision}f'
            return sign + format_string % value

    # Otherwise, pick the array and turn index into a real array index.
    if index > 0:
        array = _POSITIVE
        index = index - 1
    else:
        array = _NEGATIVE_ASCII if ascii_only else _NEGATIVE_UNICODE
        index = -index - 1

    # Overflow: If the number is too big for an SI prefix! Switch to exponential notation.
    if index >= len(array):
        return sign + _exponential_notation(value, mode, precision)

    # Normal case
    reduced = math.pow(base, delta)
    suffix = _IEC_SUFFIX if mode == Mode.IEC else ''
    format_string = f'%0.{precision}f'
    return f'{sign}{format_string % reduced}{array[index]}{suffix}'


def _exponential_notation(value: float, mode: Mode, precision: int) -> str:
    if mode == Mode.DECIMAL:
        format_str = f'%0.{precision}E'
        return format_str % value
    else:
        power = math.log2(value)
        int_power = math.floor(power)
        reduced = math.pow(2, power - int_power)
        format_str = f'%0.{precision}f'
        return f'{format_str % reduced}*2^{int_power}'


_POSITIVE = 'kMGTPEZY'
_NEGATIVE_ASCII = 'munpfazy'
_NEGATIVE_UNICODE = 'mμnpfazy'
_IEC_SUFFIX = 'i'
