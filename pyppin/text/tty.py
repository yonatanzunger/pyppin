"""Tools to do TTY color formatting in print() statements."""
import sys
from enum import IntEnum
from typing import Any, Optional


class TTY(IntEnum):
    RESET = 0
    BRIGHT = 1
    DIM = 2
    UNDERSCORE = 4
    BLINK = 5
    REVERSE = 7
    HIDDEN = 8

    # Foreground colors
    BLACK = 30
    RED = 31
    GREEN = 32
    YELLOW = 33
    BLUE = 34
    MAGENTA = 35
    CYAN = 36
    WHITE = 37

    # Background colors
    BG_BLACK = 40
    BG_RED = 41
    BG_GREEN = 42
    BG_YELLOW = 43
    BG_BLUE = 44
    BG_MAGENTA = 45
    BG_CYAN = 46
    BG_WHITE = 47


def tty(*codes: TTY, text: Optional[str] = None, file: Any = sys.stdout) -> str:
    """Generate text for print() statements with color controls in it.

    To use it, simply put commands into a string you're printing::

        print(f"{tty(TTY.RED)}Some text{tty(TTY.RESET)}")

    You can set multiple properties at a time, like bright + red. Don't forget to RESET when you
    want the effect to end, or it *will* continue to affect text even into succeeding print
    statements! If you want to wrap an entire string in an effect, we'll help you out::

        print(tty(TTY.RED, TTY.BRIGHT, text="Some text"))

    If you're using this in any function other than print(), you might want to pass the "file"
    attribute to tty, which lets the function figure out if the thing you're writing to supports
    VT100 color control codes at all. (e.g., normal text files don't!) If it doesn't, it'll suppress
    the codes for you.

    Args:
        codes: The list of display attributes to turn on
        file: The file you're writing to
        text: If given, format the entire string by wrapping it as <codes><text><reset>; the output
            of this function can be printed directly without having to worry about RESETing
            afterwards. By default, this function just returns <codes> to turn on the behavior.
    """
    if not hasattr(file, "isatty") or not file.isatty():
        return text or ""

    seq = ";".join(str(code.value) for code in codes)
    start = f"\x1b[{seq}m"

    # If text is set, return <start><text><reset>; otherwise, just return the token that sets this
    # TTY mode.
    return f"{start}{text}\x1b[0m" if text is not None else start
