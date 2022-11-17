"""An io.IOBase that lets you tee writes to multiple file targets."""

import io
from typing import Iterable, Optional, Union

from pyppin.file.dev_null import RawDevNull
from pyppin.file.types import BytesLikeObject, OpenFile

__all__ = ["tee"]


def tee(*files: OpenFile) -> OpenFile:
    """Given a collection of writable file-like objects, return a single
    file-like object, so that a write to that central object will be fanned
    out to all the passed ones.

    One sample use of this is to pass it to subprocess.Popen, so that you can
    both capture and print stdout.
    """
    if not files:
        return RawDevNull()
    if len(files) == 1:
        return files[0]

    # Make sure the files are of compatible types.
    is_text = isinstance(files[0], io.TextIOBase)
    for file in files[1:]:
        if isinstance(file, io.TextIOBase) != is_text:
            raise ValueError("All arguments to tee must be either text or binary files")

    return TextTee(*files) if is_text else RawTee(*files)  # type: ignore


class Tee(io.IOBase):
    # NB: We can't put self.children or any of the methods that depend on it in here,
    # or mypy will get very confused at the fact that the type of that variable is
    # different in each subclass. Sigh.

    def fileno(self) -> int:
        raise OSError()

    def readable(self) -> bool:
        return False

    def tell(self) -> int:
        raise NotImplementedError()

    def writable(self) -> bool:
        return True


class RawTee(Tee, io.RawIOBase):
    def __init__(self, *children: Union[io.RawIOBase, io.BufferedIOBase]) -> None:
        self.children = children

    def close(self) -> None:
        for child in self.children:
            child.close()

    @property
    def closed(self) -> bool:
        return all(child.closed for child in self.children)

    def flush(self) -> None:
        for child in self.children:
            self.flush()

    def isatty(self) -> bool:
        return all(child.isatty() for child in self.children)

    def seek(self, offset: int, whence: int = io.SEEK_SET, /) -> int:
        pos: Optional[int] = None
        for child in self.children:
            if child.seekable():
                pos = child.seek(offset, whence)
        return pos or 0

    def seekable(self) -> bool:
        return any(child.seekable() for child in self.children)

    def truncate(self, size: Optional[int] = None, /) -> int:
        pos: Optional[int] = None
        for child in self.children:
            pos = child.truncate(size)
        return pos or 0

    def write(self, b: BytesLikeObject, /) -> Optional[int]:
        pos: Optional[int] = None
        for child in self.children:
            pos = child.write(b)  # type: ignore
        return pos

    def writelines(self, lines: Iterable[BytesLikeObject], /) -> None:
        for child in self.children:
            child.writelines(lines)


class TextTee(Tee, io.TextIOBase):
    def __init__(self, *children: io.TextIOBase) -> None:
        self.children = children

    def close(self) -> None:
        for child in self.children:
            child.close()

    @property
    def closed(self) -> bool:
        return all(child.closed for child in self.children)

    def flush(self) -> None:
        for child in self.children:
            self.flush()

    def isatty(self) -> bool:
        return all(child.isatty() for child in self.children)

    def seek(self, offset: int, whence: int = io.SEEK_SET, /) -> int:
        pos: Optional[int] = None
        for child in self.children:
            if child.seekable():
                pos = child.seek(offset, whence)
        return pos or 0

    def seekable(self) -> bool:
        return any(child.seekable() for child in self.children)

    def truncate(self, size: Optional[int] = None, /) -> int:
        pos: Optional[int] = None
        for child in self.children:
            pos = child.truncate(size)
        return pos or 0

    def write(self, s: str, /) -> int:
        pos: Optional[int] = None
        for child in self.children:
            pos = child.write(s)  # type: ignore
        return pos or 0

    def writelines(self, lines: Iterable[str], /) -> None:  # type: ignore
        for child in self.children:
            child.writelines(lines)
