import argparse
import sys

import _linters  # noqa
from _common import REPO_ROOT
from _metalint import LintableFiles

if __name__ == "__main__":
    parser = argparse.ArgumentParser("linter")
    parser.add_argument("--fix", action="store_true", help="Fix files in-place")
    parser.add_argument("-v", "--verbose", action="store_true", help="Be verbose")
    parser.add_argument("files", nargs="*", help="Files to lint; default all")
    args = parser.parse_args()

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
