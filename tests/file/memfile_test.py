import io
import os
import unittest

from pyppin.file.memfile import MemFile


class MemFileTest(unittest.TestCase):
    def testMemFileNativeMethods(self) -> None:
        file = MemFile()
        self.assertEqual(0, file.size())

        # Do some reads on an empty file
        self.assertEqual((0, b""), file.pread(0, 10))
        self.assertEqual((0, b""), file.pread(5, 10))
        with self.assertRaises(ValueError):
            file.pread(0, 10, bytearray())

        buf = bytearray(10)
        self.assertEqual((0, buf), file.pread(0, 10, buf))

        # Now let's write some stuff
        self.assertEqual(5, file.pwrite(0, b"12345"))
        self.assertEqual(5, file.size())
        self.assertEqual((5, b"12345"), file.pread(0, 10))
        self.assertEqual((3, b"123"), file.pread(0, 3))
        self.assertEqual((3, b"345"), file.pread(2, 10))

        # Write after a hole
        self.assertEqual(5, file.pwrite(15, b"67890"))
        self.assertEqual(20, file.size())
        self.assertEqual(
            (20, b"12345\x00\x00\x00\x00\x00\x00\x00\x00\x00\x0067890"),
            file.pread(0, 100),
        )
        # Read starting exactly at a boundary but inside a hole
        self.assertEqual((5, bytes(5)), file.pread(8, 5))
        # Read starting exactly at a boundary inside a block
        self.assertEqual((5, b"5\x00\x00\x00\x00"), file.pread(4, 5))

    def testMemFileAsRawIO(self) -> None:
        # Let's set up some data even before we open it
        file = MemFile()
        self.assertEqual(5, file.pwrite(5, b"12345"))
        self.assertEqual((10, b"\x00\x00\x00\x00\x0012345"), file.pread(0, 20))

        # First, open it just for reading.
        with file.open("rb", buffering=0) as handle:
            # buffering=0 means we should be in raw I/O mode.
            assert isinstance(handle, io.RawIOBase)
            self.assertEqual(3, handle.seek(-7, os.SEEK_END))
            self.assertEqual(b"\x00\x00123", handle.read(5))
            with self.assertRaises(OSError):
                handle.write(b"67890")

        # OK, now let's open it for reading and writing, without truncation.
        with file.open("r+b", buffering=0) as handle:
            assert isinstance(handle, io.RawIOBase)
            self.assertEqual(3, handle.seek(-7, os.SEEK_END))
            self.assertEqual(b"\x00\x00123", handle.read(5))
            self.assertEqual(3, handle.seek(-7, os.SEEK_END))
            self.assertEqual(5, handle.write(b"67890"))
            self.assertEqual(0, handle.seek(0, os.SEEK_SET))
            self.assertEqual(b"\x00\x00\x006789045", handle.read(20))

            # Test that the file itself has changed.
            self.assertEqual((10, b"\x00\x00\x006789045"), file.pread(0, 20))

        # And finally, with truncation.
        with file.open("w+b", buffering=0) as handle:
            assert isinstance(handle, io.RawIOBase)
            self.assertEqual(0, file.size())
            self.assertEqual(b"", handle.read(20))
            self.assertEqual(3, handle.write(b"123"))
            self.assertEqual(3, handle.tell())
            self.assertEqual(0, handle.seek(0, os.SEEK_SET))
            self.assertEqual(b"123", handle.read(20))

    def testMemFileAsBufferedIO(self) -> None:
        # Let's set up some data even before we open it
        file = MemFile()
        self.assertEqual(5, file.pwrite(5, b"12345"))
        self.assertEqual((10, b"\x00\x00\x00\x00\x0012345"), file.pread(0, 20))

        # First, open it just for reading.
        with file.open("rb") as handle:
            assert isinstance(handle, io.BufferedReader)
            self.assertEqual(3, handle.seek(-7, os.SEEK_END))
            self.assertEqual(b"\x00\x00123", handle.read(5))
            with self.assertRaises(OSError):
                handle.write(b"67890")

        # OK, now let's open it for reading and writing, without truncation.
        with file.open("r+b") as handle:
            assert isinstance(handle, io.BufferedRandom)
            self.assertEqual(3, handle.seek(-7, os.SEEK_END))
            self.assertEqual(b"\x00\x00123", handle.read(5))
            self.assertEqual(3, handle.seek(-7, os.SEEK_END))
            self.assertEqual(5, handle.write(b"67890"))
            self.assertEqual(0, handle.seek(0, os.SEEK_SET))
            self.assertEqual(b"\x00\x00\x006789045", handle.read(20))

            # Test that the file itself has changed.
            self.assertEqual((10, b"\x00\x00\x006789045"), file.pread(0, 20))

        # And finally, with truncation.
        with file.open("w+b") as handle:
            assert isinstance(handle, io.BufferedRandom)
            self.assertEqual(0, file.size())
            self.assertEqual(b"", handle.read(20))
            self.assertEqual(3, handle.write(b"123"))
            self.assertEqual(3, handle.tell())
            self.assertEqual(0, handle.seek(0, os.SEEK_SET))
            self.assertEqual(b"123", handle.read(20))

    def testMemFileAsTextIO(self) -> None:
        # Let's set up some data even before we open it
        file = MemFile()
        self.assertEqual(5, file.pwrite(5, b"12345"))
        self.assertEqual((10, b"\x00\x00\x00\x00\x0012345"), file.pread(0, 20))

        # First, open it just for reading.
        with file.open("r") as handle:
            assert isinstance(handle, io.TextIOBase)
            # Text IO doesn't support end-relative seeks except "jump to EOF."
            self.assertEqual(3, handle.seek(3, os.SEEK_SET))
            self.assertEqual("\x00\x00123", handle.read(5))
            with self.assertRaises(OSError):
                handle.write("67890")

        # OK, now let's open it for reading and writing, without truncation.
        with file.open("r+") as handle:
            assert isinstance(handle, io.TextIOBase)
            self.assertEqual(3, handle.seek(3, os.SEEK_SET))
            self.assertEqual("\x00\x00123", handle.read(5))
            self.assertEqual(3, handle.seek(3, os.SEEK_SET))
            self.assertEqual(5, handle.write("67890"))
            self.assertEqual(0, handle.seek(0, os.SEEK_SET))
            self.assertEqual("\x00\x00\x006789045", handle.read(20))

            # Test that the file itself has changed.
            self.assertEqual((10, b"\x00\x00\x006789045"), file.pread(0, 20))

        # And finally, with truncation.
        with file.open("w+") as handle:
            assert isinstance(handle, io.TextIOBase)
            self.assertEqual(0, file.size())
            self.assertEqual("", handle.read(20))
            self.assertEqual(3, handle.write("123"))
            self.assertEqual(3, handle.tell())
            self.assertEqual(0, handle.seek(0, os.SEEK_SET))
            self.assertEqual("123", handle.read(20))
