import os
import stat
from pathlib import Path
from typing import Callable, Iterator, Optional, Set, Union


def findFiles(
    base: Union[str, Path],
    recursive: bool = True,
    select: Optional[Callable[[Path], bool]] = None,
) -> Iterator[Path]:
    """Scan the file system, starting at base, and return the paths of all the files we encounter.

    Args:
        base: The base file or directory from which we should start the search.
        recursive: If true, recurse into subdirectories.
        select: If given, only examine directories for which the function returns True.

    Yields:
        Paths of all matching files.
    """
    if isinstance(base, str):
        base = Path(base)
    yield from _findFiles(base, recursive=recursive, select=select, seen=set())


def _findFiles(
    base: Union[Path, os.DirEntry],
    recursive: bool,
    select: Optional[Callable[[Path], bool]],
    seen: Set[Path],
) -> Iterator[Path]:
    if isinstance(base, os.DirEntry):
        path = Path(base.path)
        isDir = base.is_dir()
        isFile = base.is_file()
    else:
        path = base
        stats = os.stat(path)
        isDir = stat.S_ISDIR(stats.st_mode)
        isFile = stat.S_ISREG(stats.st_mode)

    if isFile:
        yield path
    elif isDir:
        if path in seen:
            return
        seen.add(path)

        if select and not select(path):
            return
        for dirEntry in os.scandir(path):
            yield from _findFiles(dirEntry, recursive, select, seen)
