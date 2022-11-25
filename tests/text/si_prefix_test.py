import math
import unittest

from pyppin.text.si_prefix import Mode, si_prefix
from pyppin.text.sign import Sign


class SIPrefixTest(unittest.TestCase):
    def test_positive_prefix_decimal(self) -> None:
        self.assertEqual("0", si_prefix(0))
        self.assertEqual("100", si_prefix(100))
        self.assertEqual("100.0", si_prefix(100.0))
        self.assertEqual("1050", si_prefix(1050))
        self.assertEqual("1.2k", si_prefix(1210, precision=1))
        self.assertEqual("1100k", si_prefix(1.1e6, threshold=1.15, precision=0))
        self.assertEqual("1.1M", si_prefix(1.1e6, threshold=1.05, precision=1))
        self.assertEqual("1.2E+49", si_prefix(1.23e49))
        self.assertEqual("1.2 giga", si_prefix(1.2e9, full_names=True))

    def test_negative_prefix_decimal(self) -> None:
        self.assertEqual("100.0m", si_prefix(0.1))
        self.assertEqual("1.1m", si_prefix(1.1e-3, threshold=1.05))
        self.assertEqual("1100μ", si_prefix(1.1e-3, threshold=1.2, precision=0))
        self.assertEqual(
            "1100u", si_prefix(1.1e-3, threshold=1.2, precision=0, ascii_only=True)
        )
        self.assertEqual("1.2E-49", si_prefix(1.23e-49))
        self.assertEqual("1.2 atto", si_prefix(1.2e-18, full_names=True))

    def test_signed_value_decimal(self) -> None:
        self.assertEqual("-100", si_prefix(-100))
        self.assertEqual("-100.0", si_prefix(-100.0))
        self.assertEqual("-1050", si_prefix(-1050))
        self.assertEqual("-1.2k", si_prefix(-1210, precision=1))
        self.assertEqual("-1100k", si_prefix(-1.1e6, threshold=1.15, precision=0))
        self.assertEqual("-1.1M", si_prefix(-1.1e6, threshold=1.05, precision=1))
        self.assertEqual("-1.2E+49", si_prefix(-1.23e49))

        self.assertEqual(
            "+1.2k", si_prefix(1210, precision=1, sign=Sign.POSITIVE_AND_NEGATIVE)
        )
        self.assertEqual(
            " 1.2k", si_prefix(1210, precision=1, sign=Sign.SPACE_FOR_POSITIVE)
        )

    def test_positive_prefix_binary(self) -> None:
        self.assertEqual("0", si_prefix(0, mode=Mode.BINARY))
        self.assertEqual("100", si_prefix(100, mode=Mode.BINARY))
        # NB that this is 1.1 * 1024, not 1.1 * 1000!
        self.assertEqual("1120", si_prefix(1120, mode=Mode.BINARY, threshold=1.1))
        self.assertEqual(
            "1.09k", si_prefix(1120, mode=Mode.BINARY, threshold=1.05, precision=2)
        )
        self.assertEqual(
            "1.2*2^120", si_prefix(1.2 * math.pow(2, 120), mode=Mode.BINARY)
        )

    def test_positive_prefix_iec(self) -> None:
        self.assertEqual("0", si_prefix(0, mode=Mode.IEC))
        self.assertEqual("100", si_prefix(100, mode=Mode.IEC))
        self.assertEqual(
            "1.09Ki", si_prefix(1120, mode=Mode.IEC, threshold=1.05, precision=2)
        )
        self.assertEqual("1.2*2^120", si_prefix(1.2 * math.pow(2, 120), mode=Mode.IEC))

    def test_negative_prefix_iec(self) -> None:
        self.assertEqual("1.3μi", si_prefix(1.2e-6, mode=Mode.IEC))
        self.assertEqual("1.3*2^-20", si_prefix(1.2e-6, mode=Mode.IEC, full_names=True))

    def test_negative_prefix_binary(self) -> None:
        # Each ten powers of two is an index position, so this is 5*2^7*2^-20 = 640 * 2^-20
        self.assertEqual("640.0μ", si_prefix(5 * math.pow(2, -13), mode=Mode.BINARY))
        self.assertEqual(
            "1.2*2^-120", si_prefix(1.2 * math.pow(2, -120), mode=Mode.BINARY)
        )

    def test_corner_cases(self) -> None:
        self.assertEqual("nan", si_prefix(math.nan))
        self.assertEqual("nan", si_prefix(math.nan, mode=Mode.IEC))
        self.assertEqual("inf", si_prefix(math.inf))
