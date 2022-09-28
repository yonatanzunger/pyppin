"""An io.IOBase that behaves like /dev/null."""

import io
from typing import BinaryIO, Iterable, List, Optional, Tuple, Union, cast

from pyppin.file.types import BytesLikeObject, MutableBytesLikeObject


class DevNull(io.IOBase):
    def close(self) -> None:
        pass

    @property
    def closed(self) -> bool:
        return False

    def fileno(self) -> int:
        raise OSError()

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False

    def readable(self) -> bool:
        return False

    def seek(self, offset: int, whence: int = io.SEEK_SET, /) -> int:
        return 0

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return 0

    def truncate(self, size: Optional[int] = None, /) -> int:
        return 0

    def writable(self) -> bool:
        return True


class RawDevNull(DevNull, io.RawIOBase):
    def read(self, size: int = -1, /) -> bytes:
        return b""

    def readall(self) -> bytes:
        return b""

    def readline(self, size: Optional[int] = -1, /) -> bytes:
        return b""

    def readlines(self, hint: int = -1, /) -> List[bytes]:
        return []

    def readinto(self, b: MutableBytesLikeObject, /) -> Optional[int]:
        return None

    def write(self, b: BytesLikeObject, /) -> Optional[int]:
        return None

    def writelines(self, lines: Iterable[BytesLikeObject], /) -> None:
        pass


class TextDevNull(DevNull, io.TextIOBase):
    @property
    def encoding(self) -> Optional[str]:  # type: ignore
        return "utf-8"

    @property
    def errors(self) -> Optional[str]:  # type: ignore
        return "ignore"

    @property
    def newlines(self) -> Optional[Union[str, Tuple[str, ...]]]:  # type: ignore
        return None

    def detach(self) -> BinaryIO:
        return cast(BinaryIO, self)

    def read(self, size: Optional[int] = -1, /) -> str:
        return ""

    def readline(self, size: Optional[int] = -1, /) -> str:  # type: ignore
        return ""

    def readlines(self, hint: int = -1, /) -> List[str]:  # type: ignore
        return []

    def write(self, s: str, /) -> int:
        return 0

    def writelines(self, lines: Iterable[str], /) -> None:  # type: ignore
        pass
