"""Tools to format numbers, times, etc., using the fancy functions in :doc:`pyppin.text`.

The most general way to use this is with the Formatter class in this file. In addition to all of the
standard Python formatting, it supports a few new formats::

    TYPE        FORMAT SPEC                                             RESULT
    int, float  [[fill]align][sign][width][.precision][(threshold)]si   SI (decimal scale)
    int, float  [[fill]align][sign][width][.precision][(threshold)]sib  SI (binary scale)
    int, float  [[fill]align][sign][width][.precision][(threshold)]iec  SI (binary scale, IEC)
    timedelta   [[fill]align][sign][width]td                            time_delta_string
    timedelta   [[fill]align][width]rd                                  relative_time_string

For example, you might format a timedelta as ``{var:50rd}`` to get a 50-character wide relative time
string ("3 days from now"), or a number of bytes as ``{size:sib}B`` ("1.2GB").

The simplest way to use these formats is with pyppin.text.formatter.Formatter, which is a standard
Python `string Formatter <https://docs.python.org/3/library/string.html#custom-string-formatting>`_.
Its ``format()`` method behaves just like ``str.format()``.
"""

import string
from datetime import timedelta
from enum import Enum
from typing import Any, NamedTuple, Optional, Tuple

from pyppin.text.now_and_then import relative_time_string, time_delta_string
from pyppin.text.si_prefix import Mode, si_prefix
from pyppin.text.sign import Sign


class Formatter(string.Formatter):
    """The simple way to do this formatting: use this formatter class."""

    def format_field(self, value: Any, format_spec: str) -> str:
        spec = PyppinFormat.parse(format_spec)
        return (
            super().format_field(value, format_spec)
            if spec is None
            else spec.format(value)
        )


################################################################################################
# More advanced formatting tools below!


class Alignment(Enum):
    LEFT_ALIGN = 0
    RIGHT_ALIGN = 1
    CENTER_ALIGN = 2
    PAD_AFTER_SIGN = 3


class Format(Enum):
    SI_DECIMAL = 0
    SI_BINARY = 1
    SI_IEC = 2
    TIME_DELTA = 3
    RELATIVE_TIME = 4


class PyppinFormat(NamedTuple):
    format_spec: Format
    fill: str
    align: Alignment
    sign: Sign
    width: Optional[int]
    threshold: float
    precision: int

    @classmethod
    def parse(cls, format_spec: str) -> Optional["PyppinFormat"]:
        """Parse a format_spec.

        Returns a PyppinFormat if this is a valid Pyppin format, or None otherwise.
        """
        orig = format_spec
        # Parse an align value
        align = Alignment.LEFT_ALIGN
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

        return PyppinFormat(
            format_spec=format_type,
            align=align,
            fill=fill,
            sign=sign,
            width=width,
            precision=precision,
            threshold=threshold,
        )

    def format(self, value: object) -> str:
        if self.format_spec in (Format.SI_DECIMAL, Format.SI_BINARY, Format.SI_IEC):
            self._require(value, int, float)
            base = si_prefix(
                value,  # type: ignore
                mode=_SI_MODE[self.format_spec],
                threshold=self.threshold,
                precision=self.precision,
                sign=self.sign,
            )
        elif self.format_spec == Format.TIME_DELTA:
            self._require(value, timedelta)
            base = time_delta_string(value)  # type: ignore
        elif self.format_spec == Format.RELATIVE_TIME:
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
        elif self.align == Alignment.PAD_AFTER_SIGN:
            return base.zfill(self.width)
        elif self.align == Alignment.LEFT_ALIGN:
            return base.ljust(self.width, self.fill)
        elif self.align == Alignment.RIGHT_ALIGN:
            return base.rjust(self.width, self.fill)
        elif self.align == Alignment.CENTER_ALIGN:
            return base.center(self.width, self.fill)
        else:
            raise RuntimeError("Never happens")


_ALIGN_CHARS = {
    "<": Alignment.LEFT_ALIGN,
    ">": Alignment.RIGHT_ALIGN,
    "^": Alignment.CENTER_ALIGN,
    "=": Alignment.PAD_AFTER_SIGN,
}


_FORMAT_CHARS = {
    "si": Format.SI_DECIMAL,
    "sib": Format.SI_BINARY,
    "iec": Format.SI_IEC,
    "td": Format.TIME_DELTA,
    "rt": Format.RELATIVE_TIME,
}

_SI_MODE = {
    Format.SI_DECIMAL: Mode.DECIMAL,
    Format.SI_BINARY: Mode.BINARY,
    Format.SI_IEC: Mode.IEC,
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
