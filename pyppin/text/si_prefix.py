import math
from enum import Enum
from typing import List, Sequence, Union

from pyppin.text.sign import Sign, format_sign


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
    full_names: bool = False,
    sign: Sign = Sign.NEGATIVE_ONLY,
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
        full_names: If True, then we will print out the full words for the SI prefixes ('Mega',
            'micro', etc) rather than the one-letter abbreviations ('M', 'μ', etc).
            WARNING: There are no IEC-defined full names for negative-power prefixes, i.e. no
            IEC equivalents to milli, micro, and so on. For *short* names we can use the IEC
            convention of appending 'i' (mi, μi, etc), but there's no actual full name or rule
            for it that works. As a result, setting mode=IEC, full_names=True will treat all
            values less than one the same way prefix overflows are handled, with '2^-X' instead
            of a name.
        sign: The sign convention we should use when formatting the value.

    Returns:
        A string representation of this number, using SI prefixes.

    *** IMPORTANT NOTE ABOUT MODES ***

    Very nasty things, including physical objects crashing into each other at high speeds, have come
    from miscommunication about decimal versus binary prefixes! The IEC prefixes are an attempt to
    remedy this, by using 'ki', 'Mi', etc., for binary prefixes, and 'k', 'M', etc., for decimal
    ones, but these prefixes are only in sporadic use, possibly because the associated word forms
    ('kibi', 'mebi', etc) sound profoundly silly. However, they are very clear!

    In general, if you are unsure which to use:

        * Physical quantities, including times, should ALWAYS use decimal SI prefixes.
        * Network bandwidths are always expressed (surprise!) in *decimal*. 1Mbps = 1000000 bits per
          second, not 1048576!
        * Storage quantities in RAM and SSD should use binary or IEC prefixes.
        * Storage quantities on spinning disks are historically specified in weird made-up units,
          e.g. 1MB = 1024000 bytes. This is an artifact of disk manufacturers trying to make their
          capacities sound higher without *technically* making false or misleading statements that
          could get them sued. If you are _expressing_ storage quantities, always use binary or IEC
          prefixes; if you are _parsing_ storage quantities provided to you by a manufacturer,
          don't, measure directly instead; those numbers do not have a well-defined meaning, even if
          they seem to use SI prefixes.
    """
    assert threshold != 0
    assert precision >= 0

    # Special cases
    if value == 0:
        return "0"
    elif math.isnan(value):
        return str(value)

    # Normalize to a positive value
    if value < 0:
        is_negative = True
        value = -value
    else:
        is_negative = False

    # The other special case: infinity!
    if not math.isfinite(value):
        return format_sign(str(value), sign, is_negative)

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
            return format_sign(str(value), sign, is_negative)
        else:
            format_string = f"%0.{precision}f"
            return format_sign(format_string % value, sign, is_negative)

    # Otherwise, pick the array and turn index into a real array index.
    if index > 0:
        index = index - 1
        array = _prefix_array(mode, True, ascii_only, full_names)
    else:
        index = -index - 1
        array = _prefix_array(mode, False, ascii_only, full_names)

    # Overflow: If the number is too big for an SI prefix! Switch to exponential notation.
    if index >= len(array):
        return format_sign(
            _exponential_notation(value, mode, precision), sign, is_negative
        )

    # Normal case
    reduced = math.pow(base, delta)
    format_string = f"%0.{precision}f"
    return format_sign(f"{format_string % reduced}{array[index]}", sign, is_negative)


def _exponential_notation(value: float, mode: Mode, precision: int) -> str:
    if mode == Mode.DECIMAL:
        format_str = f"%0.{precision}E"
        return format_str % value
    else:
        power = math.log2(value)
        int_power = math.floor(power)
        reduced = math.pow(2, power - int_power)
        format_str = f"%0.{precision}f"
        return f"{format_str % reduced}*2^{int_power}"


def _prefix_array(
    mode: Mode, positive: bool, ascii_only: bool, full_names: bool
) -> Sequence[str]:
    """Return the appropriate array of prefixes to use."""
    if mode in (Mode.DECIMAL, Mode.BINARY):
        if positive:
            return _POSITIVE_LONG_SI if full_names else _POSITIVE_SI
        elif full_names:
            return _NEGATIVE_LONG_SI
        elif ascii_only:
            return _NEGATIVE_SI_ASCII
        else:
            return _NEGATIVE_SI_UNICODE

    elif positive:
        return _POSITIVE_LONG_IEC if full_names else _POSITIVE_IEC
    elif full_names:
        return _NEGATIVE_LONG_IEC
    elif ascii_only:
        return _NEGATIVE_IEC_ASCII
    else:
        return _NEGATIVE_IEC_UNICODE


_POSITIVE_SI = "kMGTPEZY"
_NEGATIVE_SI_ASCII = "munpfazy"
_NEGATIVE_SI_UNICODE = "mμnpfazy"
# Note the spaces before long forms!
_POSITIVE_LONG_SI = [
    " kilo",
    " mega",
    " giga",
    " tera",
    " peta",
    " exa",
    " zetta",
    " yotta",
]
_NEGATIVE_LONG_SI = [
    " milli",
    " micro",
    " nano",
    " pico",
    " femto",
    " atto",
    " zepto",
    " yocto",
]

_POSITIVE_IEC = ["Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi", "Yi"]
_NEGATIVE_IEC_ASCII = [x + "i" for x in _NEGATIVE_SI_ASCII]
_NEGATIVE_IEC_UNICODE = [x + "i" for x in _NEGATIVE_SI_UNICODE]
_POSITIVE_LONG_IEC = [
    " kibi",
    " mebi",
    " gibi",
    " tebi",
    " pebi",
    " exbi",
    " zebi",
    " yobi",
]
_NEGATIVE_LONG_IEC: List[str] = []  # See comment on the full_names arg to si_prefix
