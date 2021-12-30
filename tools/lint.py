import argparse
import sys
from collections import defaultdict
from typing import Dict, List

from _common import REPO_ROOT

if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)

from pyppin.bulk_import import bulkImport  # noqa
from pyppin.list_files import listFiles  # noqa

from tools.linters.common import LINTERS  # noqa

EXCLUDE_NAMES = {"build", "dist", "__pycache__"}


class LintableFiles(object):
    def __init__(self) -> None:
        self._files: Dict[str, List[str]] = defaultdict(list)

    def add(self, filename: str) -> None:
        for path in listFiles(
            filename,
            select=lambda path: path.name not in EXCLUDE_NAMES
            and not path.name.startswith("."),
        ):
            if path.suffix in LINTERS:
                self._files[path.suffix].append(str(path))

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser("linter")
    parser.add_argument("--fix", action="store_true", help="Fix files in-place")
    parser.add_argument("-v", "--verbose", action="store_true", help="Be verbose")
    parser.add_argument("files", nargs="*", help="Files to lint; default all")
    args = parser.parse_args()

    # Grab the linters
    bulkImport(f'{REPO_ROOT}/tools/linters', verbose=args.verbose, root=REPO_ROOT)

    # Grab the files to lint
    files = LintableFiles()

    if args.files:
        for file in args.files:
            files.add(file)
    else:
        files.add(REPO_ROOT)

    if args.verbose:
        files.printStats()

    # If there was a fix request, run that first.
    if args.fix:
        files.fix(verbose=args.verbose)

    if not files.lint(verbose=args.verbose):
        sys.exit(1)
