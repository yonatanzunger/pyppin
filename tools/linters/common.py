import os
import subprocess
import sys
from typing import Callable, Dict, List, NamedTuple, Optional

from tools._common import REPO_ROOT

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


def run_command(*command: str, verbose: bool = False) -> bool:
    """Helper for linters: Run a command and return whether it succeeded."""
    if verbose:
        print(" ".join(command))

    # Propagate our sys.path
    env = dict(os.environ)
    env["PYTHONPATH"] = ":".join(sys.path)

    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        if verbose:
            print("FAILURE")
        else:
            print(f"FAILURE in {' '.join(command)}")
        print()
        print(completed.stdout)
        print(completed.stderr)
        return False

    if verbose:
        print("Command succeeded")
        print(completed.stdout)
        print(completed.stderr)

    return True
