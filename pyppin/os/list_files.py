"""Recursively list all the files in a directory.

"Wait, isn't that what os.ScanDir is for?" you ask. Well... sorta. That function isn't recursive for
a reason -- correctly recursively listing things in the presence of file system links and the like
is surprisingly subtle and subject to exciting bugs. This function is here so that you never have to
worry about that again.
"""
import os
import stat
from pathlib import Path
from typing import Callable, Iterator, Optional, Set, Union


def list_files(
    base: Union[str, Path],
    recursive: bool = True,
    select: Optional[Callable[[Path], bool]] = None,
) -> Iterator[Path]:
    """List all files (recursively) within the given directory. It is guaranteed that no file will
    be listed twice, even if it appears twice due to symlinks.

    Args:
        base: The base file or directory from which we should start the search.
        recursive: If true, recurse into subdirectories.
        select: If given, only examine directories for which the function returns True.

    Yields:
        Paths of all matching files. These are absolute if `base` is absolute, or relative if `base`
        is relative. It is guaranteed that the yielded path is_relative_to(base).
    """
    if isinstance(base, str):
        base = Path(base)
    yield from _list_files(base, recursive=recursive, select=select, seen=set())


def _list_files(
    base: Union[Path, os.DirEntry],
    recursive: bool,
    select: Optional[Callable[[Path], bool]],
    seen: Set[int],
) -> Iterator[Path]:
    """The recursive meat of _list_files.

    seen is the set of *dereferenced* inode entries that we have encountered, i.e. what we see after
    following symlinks -- the true set of files and directories we're scanning.
    """
    if isinstance(base, os.DirEntry):
        path = Path(base.path)
        isDir = base.is_dir()
        isFile = base.is_file()
        # DirEntry.inode() returns the true inode number of the thing we're recursing; if it's a
        # symlink, we need to explicitly call stat to get the inode of the target.
        inode = base.inode() if not base.is_symlink() else base.stat().st_ino
    else:
        path = base
        stats = os.stat(path, follow_symlinks=True)
        isDir = stat.S_ISDIR(stats.st_mode)
        isFile = stat.S_ISREG(stats.st_mode)
        inode = stats.st_ino

    # Never process the same underlying inode twice; this both prevents double-yielding of files and
    # (more importantly) infinite loops in case of people messing about with symlinks.
    if inode in seen:
        return
    seen.add(inode)

    if isFile:
        yield path
    elif isDir:
        if select and not select(path):
            return
        with os.scandir(path) as it:
            for dirEntry in it:
                yield from _list_files(dirEntry, recursive, select, seen)
