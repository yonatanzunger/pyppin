import readline  # noqa
import sys

from _common import REPO_ROOT
from lint import main as lint_main
from pytest import console_main as test_main

from pyppin.base.import_file import import_file
from pyppin.testing.interact import interact

if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)


def default_main() -> None:
    test_main()
    # Only lint against a single version, because otherwise this is going to get unmanageable as
    # different versions' linters disagree with each other.
    if sys.version[0] == 3 and sys.version[1] == 10:
        lint_main()


def import_remaining() -> None:
    for file in sys.argv[2:]:
        import_file(file)


def main() -> None:
    """Main loop for our test harness.

    This means that you can do 'tox <cmd>' to do various things in the exact same execution
    environment that our unittests run, which is often handy.

        tox                   Run the tests and linters (default behavior)
        tox lint              Just run the linters; remaining arguments go to the linter.
        tox test              Just run the tests; remaining arguments go to pytest.
        tox py f1 f2...       Import (ie execute) the given files and stop.
    """
    main = default_main

    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "lint":
            main = lint_main
            sys.argv = [sys.argv[0]] + sys.argv[2:]
        elif command == "test":
            main = test_main  # type: ignore
            # Always insert -s when running pytests separately.
            sys.argv = [sys.argv[0], "-s"] + sys.argv[2:]
        elif command == "py":
            main = import_remaining
        elif command == "shell":
            main = interact
        else:
            raise AssertionError(f'Unknown command "{command}". Did you mean test or lint?')

    main()


if __name__ == "__main__":
    main()
