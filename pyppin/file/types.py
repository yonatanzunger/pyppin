"""Type declarations for accessing files."""

import array
import ctypes
import io
import locale
import os
from abc import ABC, abstractmethod
from mmap import mmap
from pickle import PickleBuffer
from typing import (
    Any,
    BinaryIO,
    Iterable,
    List,
    NamedTuple,
    Optional,
    Tuple,
    Union,
    cast,
)

from pyppin.base import assert_not_none

# Weird hack: The Python docs say that _CData is exposed by ctypes, but the actual CPython
# implementation doesn't do this. (The type is defined and used in _ctypes.c, it just isn't exposed
# in the Python module) However, typeshed (which is used by mypy) follows the docs, not the code,
# which means that the type signature it exposes for io.* _does_ include _CData -- which is actually
# correct, because those classes can accept _CData arguments just fine. The net result is that our
# declarations of [Mutable]BytesLikeObject have to include ctypes._CData, in order to make mypy
# happy, but (until this issue is appropriate addressed) ctypes._CData may well not exist.
# Fortunately, putting in an idiot stub definition suffices, and Python has no objection to my
# importing a module and then monkey-patching it. Which is *totally* a reasonable thing to do,
# right?
# Anyway, hopefully we can fix this in a future Python version and then get rid of this weird little
# logic.
if not hasattr(ctypes, "_CData"):

    class _CData(ABC):
        @classmethod
        @abstractmethod
        def from_buffer(cls, source: "MutableBytesLikeObject", offset: int) -> "_CData":
            ...

        @classmethod
        @abstractmethod
        def from_buffer_copy(cls, source: "BytesLikeObject", offset: int) -> "_CData":
            ...

        @classmethod
        @abstractmethod
        def from_address(cls, address: int) -> "_CData":
            ...

        @classmethod
        @abstractmethod
        def from_param(cls, obj: Any) -> "_CData":
            ...

        @classmethod
        @abstractmethod
        def in_dll(cls, library: ctypes.CDLL, name: str) -> "_CData":
            ...

    setattr(ctypes, "_CData", _CData)


"""The signature for parameter types of data operations in the Python io library."""
BytesLikeObject = Union[
    bytes, bytearray, array.array, memoryview, mmap, ctypes._CData, PickleBuffer
]
MutableBytesLikeObject = Union[
    bytearray, array.array, memoryview, mmap, ctypes._CData, PickleBuffer
]
OpenFile = Union[io.RawIOBase, io.BufferedIOBase, io.TextIOBase]


class FileLikeObject(ABC):
    """An abstract API for something that looks like a file.

    This is an API that is easy to *implement*, rather than one that's easy to use.

    You can get the easy-to-use API -- a Python IO object -- by calling open() on this object.

    NB that for objects that are fundamentally line-oriented, like TTYs, this API is not efficient
    at all, and you're better off using those directly.
    """

    @abstractmethod
    def __str__(self) -> str:
        """Return the name of the file."""
        ...

    @property
    @abstractmethod
    def readable(self) -> bool:
        """Return true if it's possible to open this file for reading."""
        ...

    @property
    @abstractmethod
    def writable(self) -> bool:
        """Return true if it's possible to open this file for writing or otherwise mutate it."""
        ...

    @property
    def fileno(self) -> int:
        """Return a file descriptor, or raise an OSError."""
        raise OSError()

    @abstractmethod
    def size(self) -> int:
        """Return the size of the file in bytes."""
        ...

    @abstractmethod
    def pread(
        self, offset: int, size: int, buffer: Optional[MutableBytesLikeObject] = None
    ) -> Tuple[int, BytesLikeObject]:
        """Read [size] bytes from absolute position [offset].

        Args:
            offset: The absolute offset from which to read.
            size: The maximum number of bytes to read.
            buffer: If given, transfer the resulting data into this bytes-like object. If not,
                allocate a fresh one.

        Returns:
            A tuple of the number of bytes read, and the object into which the data was read.

        Raises:
            OSError if anything here is invalid, including if not self.readable.
            ValueError if a buffer was provided that was too small to read into.
        """
        ...

    @abstractmethod
    def pwrite(self, offset: int, data: BytesLikeObject) -> int:
        """Write the bytes in [data] to absolute position [offset].

        Args:
            offset: The absolute offset at which to write.
            data: The data to write.

        Returns:
            The number of bytes actually written.

        Raises: OSError if anything here is invalid, including if not self.writable.
        """
        ...

    @abstractmethod
    def truncate(self, length: int) -> int:
        """Truncate the file.

        Args:
            length: The new length of the file. If this is >= the current length of the file,
                do nothing.

        Returns:
            The new size of the file.
        """
        ...

    def open(
        self,
        mode: str = "r",
        buffering: int = -1,
        encoding: Optional[str] = None,
        errors: Optional[str] = None,
        newline: Optional[str] = None,
    ) -> OpenFile:
        """Open a file-like object with a normal Python file API.

        Apart from the 'file' argument, all the arguments are identical to those of the built-in
        function `open() <https://docs.python.org/3/library/functions.html#open>`_.

        Note that the 'create'-related modes (such as x) are ignored here, since the file-like
        object presumably already exists!

        The return type, alas, depends on the mode.
        """
        options = OpenOptions.parse(
            mode=mode,
            buffering=buffering,
            encoding=encoding,
            errors=errors,
            newline=newline,
            isatty=False,
        )
        rawfile = _UnbufferedBinaryFileHandle(self, options)
        if not options.byte_buffering:
            assert options.binary
            return rawfile

        buffered: io.BufferedIOBase
        if options.readable and options.writable:
            buffered = io.BufferedRandom(rawfile, options.byte_buffering)
        elif options.readable:
            buffered = io.BufferedReader(rawfile, options.byte_buffering)
        else:
            buffered = io.BufferedWriter(rawfile, options.byte_buffering)

        if options.binary:
            return buffered

        # Silly thing: TextIOWrapper expects BinaryIO, but BufferedIOBase -- the type it actually
        # wants -- is *not* declared as an implementation of that abstract class. Sigh.
        return io.TextIOWrapper(
            cast(BinaryIO, buffered),
            encoding=options.encoding,
            errors=options.error_handling,
            newline=options.newline_handling,
            line_buffering=options.line_buffering,
            write_through=True,
        )


class OpenOptions(NamedTuple):
    """A parsed version of all of the options sent to open().

    See the `function spec <https://docs.python.org/3/library/functions.html#open>`_ for the exact
    logic definition.
    """

    readable: bool = False
    """True if the file should be opened for reading."""

    writable: bool = False
    """True if the file should be opened for writing."""

    create: bool = False
    """True if the file should be created if it doesn't already exist."""

    truncate: bool = False
    """True if the file should be truncated to zero length on opening."""

    seek_to_end: bool = False
    """True if we should seek to the end of the file immediately after opening."""

    binary: bool = False
    """True if the file should be opened in binary (rather than text) mode."""

    encoding: Optional[str] = None
    """The encoding to use. Always None in binary mode, and not None in text mode."""

    error_handling: Optional[str] = None
    """The encoding error handling mechanism. Non-None in text mode."""

    newline_handling: Optional[str] = None
    """The newline handling mechanism. Non-None in text mode."""

    line_buffering: bool = False
    """If true, do line-level buffering on the file. Only available in text mode."""

    byte_buffering: Optional[int] = None
    """In binary mode, this is not None and is the size of the buffer to be used."""

    @staticmethod
    def parse(
        mode: str = "r",
        buffering: int = -1,
        encoding: Optional[str] = None,
        errors: Optional[str] = None,
        newline: Optional[str] = None,
        isatty: bool = False,
    ) -> "OpenOptions":
        """Parse the mode argument of open()."""
        readable = False
        writable = False
        create = False
        truncate = False
        seek_to_end = False
        binary = False
        line_buffering = False
        byte_buffering: Optional[int] = None

        for char in mode:
            if char == "r":
                readable = True
            elif char == "w":
                writable = True
                truncate = True
                create = True
            elif char == "x":
                create = False
            elif char == "a":
                writable = True
                truncate = False
                seek_to_end = True
            elif char == "b":
                binary = True
            elif char == "t":
                binary = False
            elif char == "+":
                readable = True
                writable = True
            elif char == "U":
                pass
            else:
                raise ValueError(f'Unknown character "{char}" in mode "{mode}"')

        if truncate and not writable:
            raise ValueError("A file cannot be truncated if it is not writable!")

        if encoding is None and not binary:
            encoding = locale.getpreferredencoding()
        if errors is not None and binary:
            raise ValueError("errors can only be used in text mode")
        if buffering == -1:
            if not binary and isatty:
                line_buffering = True
            else:
                byte_buffering = io.DEFAULT_BUFFER_SIZE
        elif buffering == 1:
            if binary:
                raise ValueError("Line buffering can only be used in text mode")
            line_buffering = True
        elif buffering == 0:
            if not binary:
                raise ValueError("Unbuffered access can only be used in binary mode")
        else:
            byte_buffering = buffering

        # Text IO requires an underlying buffered IO object.
        if not binary and byte_buffering is None:
            byte_buffering = io.DEFAULT_BUFFER_SIZE

        return OpenOptions(
            readable=readable,
            writable=writable,
            create=create,
            truncate=truncate,
            seek_to_end=seek_to_end,
            binary=binary,
            encoding=encoding,
            error_handling=errors,
            newline_handling=newline,
            line_buffering=line_buffering,
            byte_buffering=byte_buffering,
        )


class _UnbufferedBinaryFileHandle(io.RawIOBase):
    """The implementation of a Python unbuffered I/O API to a FileLikeObject.

    This the glue between the easy-to-implement API and the easy-to-use one. You don't invoke this
    directly; it's created for you by FileLikeObject.open().
    """

    def __init__(self, file: FileLikeObject, options: OpenOptions) -> None:
        if options.readable and not file.readable:
            raise OSError(f'"{file}" is not readable')
        if options.writable and not file.writable:
            raise OSError(f'"{file}" is not writable')

        if options.writable and options.truncate:
            file.truncate(0)

        self.file = file
        self._readable = options.readable
        self._writable = options.writable
        self._pos = file.size() if options.seek_to_end else 0
        self._closed = False

    def close(self) -> None:
        self._closed = True

    @property
    def closed(self) -> bool:
        return self._closed

    def fileno(self) -> int:
        return self.file.fileno

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False

    def readable(self) -> bool:
        return self._readable

    def readline(self, size: Optional[int] = -1) -> bytes:
        # TODO
        return bytes()

    def readlines(self, hint: Optional[int] = -1) -> List[bytes]:
        # TODO
        return []

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        if whence == os.SEEK_SET:
            self._pos = offset
        elif whence == os.SEEK_CUR:
            self._pos += offset
        elif whence == os.SEEK_END:
            self._pos = self.file.size() + offset
        return self._pos

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def truncate(self, size: Optional[int] = None) -> int:
        self._check(True)
        if size is None:
            size = self._pos
        if self._pos > size:
            self._pos = size
        return self.file.truncate(size)

    def writable(self) -> bool:
        return self._writable

    def writelines(self, lines: Iterable[BytesLikeObject]) -> None:
        for line in lines:
            self.write(line)

    def read(self, size: Optional[int] = -1) -> Optional[bytes]:
        self._check(False)
        if size is None or size == -1:
            size = self.file.size() - self._pos
        bytes_read, result = self.file.pread(self._pos, size)
        self._pos += bytes_read
        return bytes(result)  # type: ignore

    def readall(self) -> bytes:
        return assert_not_none(self.read())

    def readinto(self, b: MutableBytesLikeObject) -> int:
        self._check(False)
        actual_size, _ = self.file.pread(self._pos, len(b), buffer=b)  # type: ignore
        self._pos += actual_size
        return actual_size

    def write(self, b: BytesLikeObject) -> int:
        self._check(True)
        bytes_written = self.file.pwrite(self._pos, b)
        self._pos += bytes_written
        return bytes_written

    def pread(
        self, offset: int, size: int, buffer: Optional[MutableBytesLikeObject] = None
    ) -> Tuple[int, BytesLikeObject]:
        """Read from an absolute position without changing the current r/w offset.

        Args:
            offset: The absolute offset from which to read.
            size: The number of bytes to read.
            buffer: An optional buffer into which to read the data; if not given, one will be
                created.

        Returns:
            The number of bytes actually read.
            The buffer containing the data.
        """
        self._check(False)
        return self.file.pread(offset, size, buffer)

    def pwrite(self, offset: int, data: BytesLikeObject) -> int:
        """Write to an absolute position without changing the current r/w offset.

        Args:
            offset: The absolute offset at which to write.
            data: The bytes to write.

        Returns:
            The number of bytes actually written.
        """
        self._check(True)
        return self.file.pwrite(offset, data)

    def _check(self, write: bool) -> None:
        if self._closed:
            raise OSError(f'"{self.file}" is closed')
        if write and not self._writable:
            raise OSError(f'"{self.file}" is not writable')
        if not write and not self._readable:
            raise OSError(f'"{self.file}" is not readable')
