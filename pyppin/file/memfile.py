"""Allow access to a single block of RAM with multiple file API handles."""

from typing import Optional, Tuple

from pyppin.file.types import (
    BytesLikeObject,
    FileLikeObject,
    MutableBytesLikeObject,
    OpenFile,
)


class MemFile(FileLikeObject):
    """Access a block of RAM as a file-like object.

    Unlike using io.BytesIO or io.StringIO, which do similar things, a MemFile lets you create a
    single block of memory and have *multiple* things refer to the same block by open()ing it. This
    is especially useful if you need to make the same chunk of data simultaneously available to two
    API's that each expect files. (Alas, a common issue with cloud API's)

    The simplest way to use this object is to just allocate it and call open() on it to get as many
    file handles (of as many types) as you need.

    This class is thread-compatible: it provides no synchronization of its own, and (just like with
    files on local disk) if multiple threads are reading and writing a file at once, you'd better
    coordinate that.
    """

    def __init__(self, name: str = "memfile") -> None:
        self._name = name
        self._data = bytearray()

    def __str__(self) -> str:
        return self._name

    def open(
        self,
        mode: str = "r",
        buffering: int = -1,
        encoding: Optional[str] = None,
        errors: Optional[str] = None,
        newline: Optional[str] = None,
    ) -> OpenFile:
        """Create a new file handle which accesses the data in this MemFile.

        The resulting object is of the appropriate type (io.RawIO, io.BufferedIO, or io.TextIO)
        depending on the arguments in the usual fashion.

        Note that there is no inherent thread-safety in these files: If multiple threads are reading
        and writing the same MemFile at once, they need to synchronize their access to it, just like
        they would for ordinary files on disk.
        """
        return super().open(
            mode=mode,
            buffering=buffering,
            encoding=encoding,
            errors=errors,
            newline=newline,
        )

    @property
    def bytes(self) -> bytearray:
        """Raw access to the underlying byte array."""
        return self._data

    @property
    def readable(self) -> bool:
        return True

    @property
    def writable(self) -> bool:
        return True

    def size(self) -> int:
        return len(self._data)

    def pread(
        self, offset: int, size: int, buffer: Optional[MutableBytesLikeObject] = None
    ) -> Tuple[int, BytesLikeObject]:
        assert offset >= 0
        assert size >= 0

        if buffer is not None:
            # Transform this into a byte buffer, no matter what format we received (e.g. an array of
            # something)
            buffer = memoryview(buffer).cast("B")
            bufsize = len(buffer)
            if size > bufsize:
                raise ValueError(
                    f"Buffer too small: Tried to read {size} bytes into a buffer of size "
                    f"{bufsize}"
                )
        else:
            buffer = bytearray()

        read_size = max(0, min(size, self.size() - offset))
        buffer[0:read_size] = self._data[offset : offset + read_size]
        return read_size, buffer

    def pwrite(self, offset: int, data: BytesLikeObject) -> int:
        data = memoryview(data).cast("B")
        size = len(data)
        if offset >= len(self._data):
            self._data = self._data + bytes(offset - len(self._data)) + data
        else:
            self._data[offset : offset + size] = data
        return size

    def truncate(self, length: int) -> int:
        if length < self.size():
            self._data = self._data[:length]
        return self.size()
