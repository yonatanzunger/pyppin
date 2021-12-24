import os
import stat
import subprocess
import sys
from collections import defaultdict
from typing import Callable, Dict, List, NamedTuple, Optional, Set, Union

from _common import REPO_ROOT

EXCLUDE_NAMES = {"build", "dist"}


# A "fix" function is a function that takes a list of filenames and a verbosity and tries to
# fix any fixable lint errors.
FixFunction = Callable[[List[str], bool], None]

# A "lint" function is a function that takes a list of filenames and a verbosity and returns
# True if they're properly formatted, and prints out errors on stdout and returns False
# otherwise.
LintFunction = Callable[[List[str], bool], bool]


class _FileLint(NamedTuple):
    linters: List[LintFunction]
    fixers: List[FixFunction]


LINTERS: Dict[str, _FileLint] = {}


def linter(
    filetypes: List[str],
    lint: Optional[LintFunction] = None,
    fix: Optional[FixFunction] = None,
) -> None:
    """Declare how to lint files of a given type. This function is normally invoked at import.

    Args:
        filetypes: A list of file suffixes (e.g. "py") of files that should be handled by this
            linter.
        lint: An optional lint function to check if a file of this type is valid.
        fix: An optional fix function to do its best of fixing a file of this type.
    """
    global LINTERS
    for filetype in filetypes:
        if filetype not in LINTERS:
            LINTERS[filetype] = _FileLint(list(), list())
        if lint is not None:
            LINTERS[filetype].linters.append(lint)
        if fix is not None:
            LINTERS[filetype].fixers.append(fix)


def runCommand(*command: str, verbose: bool=False) -> bool:
    """Helper for linters: Run a command and return whether it succeeded."""
    if verbose:
        print(" ".join(command))
    pythonPath = ":".join(sys.path)
    try:
        subprocess.check_call(
            [f'PYTHONPATH="{pythonPath}"', *command], cwd=REPO_ROOT, shell=True
        )
        return True
    except subprocess.CalledProcessError:
        if verbose:
            print("Failed!")
        return False


class LintableFiles(object):
    def __init__(self) -> None:
        self._files: Dict[str, List[str]] = defaultdict(list)
        self._scannedDirs: Set[str] = set()

    def add(self, filename: Union[str, os.DirEntry]) -> None:
        """Add a file or directory to the list of files to be linted."""
        if isinstance(filename, str):
            name = os.path.abspath(filename)
            stats = os.stat(name)
            isDir = stat.S_ISDIR(stats.st_mode)
            isFile = stat.S_ISREG(stats.st_mode)
        else:
            name = filename.path
            isDir = filename.is_dir()
            isFile = filename.is_file()

        if isFile:
            parts = os.path.basename(name).rsplit(".", 1)
            if len(parts) < 2:
                return

            filetype = parts[-1]
            if filetype not in LINTERS:
                return
            self._files[filetype].append(name)

        elif isDir:
            if name in self._scannedDirs:
                return
            for dirEntry in os.scandir(name):
                if dirEntry.name in EXCLUDE_NAMES or dirEntry.name.startswith("."):
                    continue
                self.add(dirEntry)

    def _count(self, num: int, name: str) -> str:
        if num == 1:
            return f"1 {name}"
        return f"{num} {name}s"

    def printStats(self) -> None:
        for extension, filenames in sorted(self._files.items()):
            print(
                f"Type [{extension}]: "
                f"{self._count(len(filenames), 'file')}, "
                f"{self._count(len(LINTERS[extension].linters), 'linter')}, "
                f"{self._count(len(LINTERS[extension].fixers), 'fixer')}."
            )

    def fix(self, verbose: bool = False) -> None:
        """Fix any files that can be fixed. (Call this *before* you lint)"""
        for filetype, filenames in self._files.items():
            assert filetype in LINTERS
            for fixer in LINTERS[filetype].fixers:
                fixer(filenames, verbose)

    def lint(self, verbose: bool = False) -> bool:
        """Check all the files for lint errors, print out errors and returning True iff
        everything is good.
        """
        ok = True
        for filetype, filenames in self._files.items():
            assert filetype in LINTERS
            for linter in LINTERS[filetype].linters:
                if not linter(filenames, verbose):
                    ok = False
                    # But don't short-circuit!
        return ok
