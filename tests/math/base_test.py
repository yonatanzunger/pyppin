import unittest

from pyppin.math import round_up_to


class MathBaseTest(unittest.TestCase):
    def testRoundUpTo(self) -> None:
        self.assertEqual(3.2, round_up_to(3.1, 0.2))
        self.assertEqual(3.2, round_up_to(3.2, 0.2))
