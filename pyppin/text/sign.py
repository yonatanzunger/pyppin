"""Some shared logic for defining sign-printing conventions."""

from enum import Enum
from typing import Tuple


class Sign(Enum):
    """Equivalent to printf -: Show a minus sign for negative numbers and nothing for positive."""

    NEGATIVE_ONLY = 0
    """Equivalent to printf +: Show signs for both positive and negative numbers."""
    POSITIVE_AND_NEGATIVE = 1
    """Equivalent to printf space: Show minus sign for negative and space for positive."""
    SPACE_FOR_POSITIVE = 2

    @classmethod
    def parse(cls, format_spec: str) -> Tuple["Sign", str]:
        """Parse a leading printf sign from a format_spec.

        Returns:
            Sign: The sign that should be used.
            str: The remaining format_spec.
        """
        if format_spec and format_spec[0] in _SIGN_CHARS:
            return _SIGN_CHARS[format_spec[0]], format_spec[1:]
        else:
            return Sign.NEGATIVE_ONLY, format_spec


def format_sign(formatted_unsigned: str, sign_mode: Sign, is_negative: bool) -> str:
    """Add the sign characters, as appropriate, to the given string."""
    padding = "-" if is_negative else _SIGN_PADDING[sign_mode]
    return padding + formatted_unsigned


_SIGN_CHARS = {
    "-": Sign.NEGATIVE_ONLY,
    "+": Sign.POSITIVE_AND_NEGATIVE,
    " ": Sign.SPACE_FOR_POSITIVE,
}


_SIGN_PADDING = {
    Sign.NEGATIVE_ONLY: "",
    Sign.POSITIVE_AND_NEGATIVE: "+",
    Sign.SPACE_FOR_POSITIVE: " ",
}
