"""Format numbers using SI prefixes, turning 1,234,567 into 1.2M."""

import math
from enum import Enum
from typing import List, Sequence, Union

from pyppin.text.sign import Sign, format_sign


class Mode(Enum):
    """The kinds of units to use: what does "1k" mean?"""

    DECIMAL = 0
    """Decimal SI units; 1k = 1,000."""

    BINARY = 1
    """Binary SI units; 1k = 1,024, but use the ordinary symbols k, M, etc."""

    IEC = 2
    """IEC units; 1k = 1,024, but write ki, Mi, etc., as per the IEC80000 standard."""


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

    Numbers beyond the range of SI prefixes will be rendered as 1.2E243 (decimal) or 1.2*2^99
    (binary).

    Args:
        value: The number to be formatted.
        mode: Whether to use decimal or binary SI units.
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
        sign: The sign convention we should use when formatting the value.

    Returns:
        A string representation of this number, using SI prefixes.

    Note
    ====
    There are no IEC-defined full names for negative-power prefixes, i.e. no
    IEC equivalents to milli, micro, and so on. For *short* names we can use the IEC
    convention of appending 'i' (mi, μi, etc), but for the long names, there's no analogous
    rule that works. As a result, setting ``mode=IEC, full_names=True`` will treat all
    values less than one the same way prefix overflows are handled, with ``2^-X`` instead
    of a name.

    Warning
    =======

    Very nasty things, including physical objects crashing into each other at high speeds, have
    happened because of miscommunications about decimal (1k = 1,000) and binary (1k = 1,024)
    prefixes.

    The IEC prefixes are an attempt to fix this, by using 'ki', 'Mi', etc., for binary prefixes, and
    reserving 'k', 'M', etc., for decimal ones. However, IEC notation is only in sporadic use,
    possibly because the associated word forms ('kibi', 'Mebi', etc) sound rather silly. This means
    that if you encounter a numeric prefix in the wild, you need to check to see which one you are
    seeing!

    In general, when IEC prefixes aren't in use, there are some very important conventions to
    follow:

        * Physical quantities, including times, should always use decimal SI prefixes.
        * Storage quantities (in RAM or on disk) should always use binary or IEC prefixes.
        * Network capacities should always use decimal (surprise!) IEC prefixes.

    There are a few surprises hiding in the rules above:

        * Because network capacities are measured in decimal units while data is measured in binary
          units, transmitting 1MB of data (1,048,576 bytes) at 1MBps (1,000,000 bytes per second)
          takes 1.049 seconds, not one second.
        * Network capacities are measured in three different but similar-sounding units: Bps (bytes
          per second of data transmitted), bps (bits per second of data transmitted), and baud
          (line-level transitions per second, i.e. raw bits on the wire per second, including bits
          used for things like error-correcting codes and other things that aren't actual data
          transmitted). bps (note the lowercase!) is by far the most common, to the extent that if
          anyone ever talks to you about Bps you should check if they actually meant that.
          Transmitting 1MB of data at 1Mbps takes 8.39 seconds.
        * Historically, storage quantities on spinning disks were reported by manufacturers in weird
          units that were neither decimal nor binary, like "1MB = 1,024,000 bytes". This is an
          artifact of them trying to make their capacities sound higher without *technically* making
          false or misleading statements. If you encounter numbers like these in the wild, take them
          with a very large grain of salt.
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


_POSITIVE_SI = "kMGTPEZYRQ"
_NEGATIVE_SI_ASCII = "munpfazyrq"
_NEGATIVE_SI_UNICODE = "mμnpfazyrq"
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
    " ronna",
    " quetta",
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
    " ronto",
    " quecto",
]

_POSITIVE_IEC = ["Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi", "Yi", "Ri", "Qi"]
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
    " ronni",
    " quetti",
]
_NEGATIVE_LONG_IEC: List[str] = []  # See comment on the full_names arg to si_prefix
