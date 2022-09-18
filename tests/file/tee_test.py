import io
import unittest

from pyppin.file.tee import tee


class TeeTest(unittest.TestCase):
    def testTextTee(self) -> None:
        a = io.StringIO()
        b = io.StringIO()
        t = tee(a, b)

        assert isinstance(t, io.TextIOBase)
        t.write("foo")
        t.write("bar")

        self.assertEqual("foobar", a.getvalue())
        self.assertEqual("foobar", b.getvalue())
