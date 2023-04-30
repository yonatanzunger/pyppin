import unittest

from pyppin.text.tty import TTY, tty


class VT100File(object):
    def isatty(self) -> bool:
        return True


class NonVT100File(object):
    def isatty(self) -> bool:
        return False


class TTYTest(unittest.TestCase):
    def test_vt100(self) -> None:
        self.assertEqual("\x1b[1;31m", tty(TTY.BRIGHT, TTY.RED, file=VT100File()))
        self.assertEqual(
            "\x1b[1;31mHello World\x1b[0m",
            tty(TTY.BRIGHT, TTY.RED, text="Hello World", file=VT100File()),
        )

    def test_non_vt100(self) -> None:
        self.assertEqual("", tty(TTY.BRIGHT, TTY.RED, file=NonVT100File()))
        self.assertEqual(
            "Hello World",
            tty(TTY.BRIGHT, TTY.RED, text="Hello World", file=NonVT100File()),
        )


if __name__ == "__main__":
    unittest.main()
