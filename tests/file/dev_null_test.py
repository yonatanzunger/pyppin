import unittest

from pyppin.file.dev_null import RawDevNull, TextDevNull


class DevNullTest(unittest.TestCase):
    def testTextDevNull(self) -> None:
        dn = TextDevNull()
        self.assertEqual("", dn.read())
        self.assertEqual(0, dn.write("foobar"))

    def testBinaryDevNull(self) -> None:
        dn = RawDevNull()
        self.assertEqual(b"", dn.read())
        self.assertIsNone(dn.write(b"foobar"))
