import unittest

from pyppin.text.formatter import Formatter


class FormatterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.formatter = Formatter()

    def test_si_number(self) -> None:
        num = 1120.0
        self.assertEqual("1.1k", self.formatter.format("{num:si}", num=num))
        self.assertEqual("1120.0", self.formatter.format("{num:sib}", num=num))
        # Pass an int argument, get an int result
        self.assertEqual("1120", self.formatter.format("{num:sib}", num=1120))
        self.assertEqual("1120", self.formatter.format("{num:.0sib}", num=num))
        self.assertEqual("+1.1Ki", self.formatter.format("{num:+(1.05)iec}", num=num))
        # Normal floating-point formats work, too
        self.assertEqual("1.12e+03", self.formatter.format("{num:0.2e}", num=num))
