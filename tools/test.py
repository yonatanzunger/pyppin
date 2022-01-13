import sys

from _common import REPO_ROOT
from lint import main as lint_main
from pytest import console_main as test_main

if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)

from pyppin.testing.interact import interact


def main() -> None:
    """Main loop for our test harness.

    If no arguments are given, run the tester followed by the linter.
    If the first argument is either 'test' or 'lint', run just that, with
    any remaining arguments passed to it.
    """
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "lint":
            main = lint_main
            sys.argv = [sys.argv[0]] + sys.argv[2:]
        elif command == "test":
            main = test_main  # type: ignore
            # Always insert -s when running pytests separately.
            sys.argv = [sys.argv[0], "-s"] + sys.argv[2:]
        elif command == "shell":
            main = interact  # type: ignore
        else:
            raise AssertionError(
                f'Unknown command "{command}". Did you mean test or lint?'
            )
        main()
    else:
        test_main()
        lint_main()


if __name__ == "__main__":
    main()
