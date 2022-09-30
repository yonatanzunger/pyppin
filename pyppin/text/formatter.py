"""Tools to format numbers, times, etc., using the fancy functions in :doc:`pyppin.text`."""

import string
from datetime import timedelta
from enum import Enum
from typing import Any, NamedTuple, Optional, Tuple

from pyppin.text.now_and_then import relative_time_string, time_delta_string
from pyppin.text.si_prefix import Mode, si_prefix
from pyppin.text.sign import Sign

# The "advanced" interface to this class is really specialized, there are very few cases where
# anyone would want to import that.
__all__ = ["Formatter"]


class Formatter(string.Formatter):
    """A ``string.Formatter`` that includes several new formatting options.

    Provides a Python `string Formatter
    <https://docs.python.org/3/library/string.html#custom-string-formatting>`_ which, in addition
    to all of the standard Python formatting, supports a few new formats:

    +------------+----------------------+--------------------------------------------------------+
    | Type       | Format specification | Renders as                                             |
    +============+======================+========================================================+
    | int, float | ``:si``              | :doc:`SI (decimal scale) <pyppin.text.si_prefix>`      |
    +------------+----------------------+--------------------------------------------------------+
    | int, float | ``:sib``             | :doc:`SI (binary scale) <pyppin.text.si_prefix>`       |
    +------------+----------------------+--------------------------------------------------------+
    | int, float | ``:iec``             | :doc:`SI (binary scale, IEC) <pyppin.text.si_prefix>`  |
    +------------+----------------------+--------------------------------------------------------+
    | timedelta  | ``:td``              | :doc:`time_delta_string <pyppin.text.now_and_then>`    |
    +------------+----------------------+--------------------------------------------------------+
    | timedelta  | ``:rd``              | :doc:`relative_time_string <pyppin.text.now_and_then>` |
    +------------+----------------------+--------------------------------------------------------+

    For example, you might format a timedelta as ``{delta:rd}`` to get a string like "3 days from
    now", or a number of bytes as ``{size:sib}B`` to get a string like "1.2GB".

    To use this class, simply create one of these objects and use its ``format()`` method the way
    you would normally use ``str.format()``.

    Options
    =======
    A wide range of options are available for each of these formats.

    * ``si``, ``sib``, and ``iec`` accept ``[[fill]align][sign][width][.precision][(threshold)]``
      as options. (e.g., ``{variable:>+30.2(1.2)si}`` would print ``variable`` as a decimal-scale
      SI number, right-aligned in a 30-character wide block, showing a plus or minus sign, two
      points after the decimal, and using a threshold of 1.2.) The fill, align, sign, and width
      arguments are identical to the standard ones defined in Python's `custom string formatting
      <https://docs.python.org/3/library/string.html#custom-string-formatting>`_ rules; the
      precision and threshold are defined by the :doc:`si_prefix <pyppin.text.si_prefix>` function.
    * ``td`` accepts ``[[fill]align][sign][width]``, using the standard Python meanings for each;
      e.g., ``{delta:+30td}`` would print ``delta`` in a 30-character wide box with a plus or minus
      sign.
    * ``rd`` accepts ``[[fill]align][width]``, using the standard Python meanings for each.
    """

    def format_field(self, value: Any, format_spec: str) -> str:
        spec = _PyppinFormat.parse(format_spec)
        return (
            super().format_field(value, format_spec)
            if spec is None
            else spec.format(value)
        )


################################################################################################
# More advanced formatting tools below!


class _Alignment(Enum):
    LEFT_ALIGN = 0
    RIGHT_ALIGN = 1
    CENTER_ALIGN = 2
    PAD_AFTER_SIGN = 3


class _Format(Enum):
    SI_DECIMAL = 0
    SI_BINARY = 1
    SI_IEC = 2
    TIME_DELTA = 3
    RELATIVE_TIME = 4


class _PyppinFormat(NamedTuple):
    format_spec: _Format
    fill: str
    align: _Alignment
    sign: Sign
    width: Optional[int]
    threshold: float
    precision: int

    @classmethod
    def parse(cls, format_spec: str) -> Optional["_PyppinFormat"]:
        """Parse a format_spec.

        Returns a _PyppinFormat if this is a valid Pyppin format, or None otherwise.
        """
        orig = format_spec
        # Parse an align value
        align = _Alignment.LEFT_ALIGN
        fill = " "
        if format_spec and format_spec[0] in _ALIGN_CHARS:
            align = _ALIGN_CHARS[format_spec[0]]
            format_spec = format_spec[1:]
        elif len(format_spec) >= 2 and format_spec[1] in _ALIGN_CHARS:
            align = _ALIGN_CHARS[format_spec[1]]
            fill = format_spec[0]
            format_spec = format_spec[2:]

        # Parse a sign value
        sign, format_spec = Sign.parse(format_spec)

        # Parse a width value by pulling off an int
        width, format_spec = _leading_int(format_spec)

        # Parse a precision value
        if format_spec.startswith("."):
            precision, format_spec = _leading_int(format_spec[1:], default=1)
        else:
            precision = 1
        assert precision is not None

        # Parse a threshold value
        if format_spec.startswith("("):
            end = format_spec.find(")")
            if end == -1:
                raise ValueError(
                    f"Bad format spec '{orig}': Unmatched ( in threshold value"
                )
            threshold = float(format_spec[1:end])
            format_spec = format_spec[end + 1 :]
        else:
            threshold = 1.1

        if format_spec not in _FORMAT_CHARS:
            # This isn't one of our formats!
            return None

        format_type = _FORMAT_CHARS[format_spec]

        return _PyppinFormat(
            format_spec=format_type,
            align=align,
            fill=fill,
            sign=sign,
            width=width,
            precision=precision,
            threshold=threshold,
        )

    def format(self, value: object) -> str:
        if self.format_spec in (_Format.SI_DECIMAL, _Format.SI_BINARY, _Format.SI_IEC):
            self._require(value, int, float)
            base = si_prefix(
                value,  # type: ignore
                mode=_SI_MODE[self.format_spec],
                threshold=self.threshold,
                precision=self.precision,
                sign=self.sign,
            )
        elif self.format_spec == _Format.TIME_DELTA:
            self._require(value, timedelta)
            base = time_delta_string(value)  # type: ignore
        elif self.format_spec == _Format.RELATIVE_TIME:
            self._require(value, timedelta)
            base = relative_time_string(value)  # type: ignore
        else:
            raise RuntimeError("Never happens")

        return self._pad(base)

    def _require(self, value: object, *types: type) -> None:
        if not any(isinstance(value, type) for type in types):
            raise ValueError(
                f"Cannot format {type(value).__name__} as {self.format_spec}"
            )

    def _pad(self, base: str) -> str:
        if self.width is None:
            return base
        elif self.align == _Alignment.PAD_AFTER_SIGN:
            return base.zfill(self.width)
        elif self.align == _Alignment.LEFT_ALIGN:
            return base.ljust(self.width, self.fill)
        elif self.align == _Alignment.RIGHT_ALIGN:
            return base.rjust(self.width, self.fill)
        elif self.align == _Alignment.CENTER_ALIGN:
            return base.center(self.width, self.fill)
        else:
            raise RuntimeError("Never happens")


_ALIGN_CHARS = {
    "<": _Alignment.LEFT_ALIGN,
    ">": _Alignment.RIGHT_ALIGN,
    "^": _Alignment.CENTER_ALIGN,
    "=": _Alignment.PAD_AFTER_SIGN,
}


_FORMAT_CHARS = {
    "si": _Format.SI_DECIMAL,
    "sib": _Format.SI_BINARY,
    "iec": _Format.SI_IEC,
    "td": _Format.TIME_DELTA,
    "rt": _Format.RELATIVE_TIME,
}

_SI_MODE = {
    _Format.SI_DECIMAL: Mode.DECIMAL,
    _Format.SI_BINARY: Mode.BINARY,
    _Format.SI_IEC: Mode.IEC,
}


def _leading_int(s: str, default: Optional[int] = None) -> Tuple[Optional[int], str]:
    """Pull off a leading int from s if available, return the int and the remainder."""
    i = 0
    for i, c in enumerate(s):
        if not c.isdigit():
            break
    if i:
        return int(s[:i]), s[i:]
    else:
        return default, s
