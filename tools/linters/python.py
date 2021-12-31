from typing import List

from tools.linters.common import linter, run_command


def lint_py_files(files: List[str], verbose: bool) -> bool:
    if not files:
        return True

    ok = True
    if not run_command("python", "-m", "flake8", *files, verbose=verbose):
        ok = False
    if not run_command(
        "python", "-m", "isort", "--atomic", "--check-only", *files, verbose=verbose
    ):
        ok = False
    if not run_command("python", "-m", "black", "--check", *files, verbose=verbose):
        ok = False
    if not run_command("python", "-m", "mypy", *files, verbose=verbose):
        ok = False

    print(f'Lint of {len(files)} Python files {"successful" if ok else "failed"}!')
    return ok


def fix_py_files(files: List[str], verbose: bool) -> None:
    if not files:
        return

    run_command("python", "-m", "isort", "--atomic", *files, verbose=verbose)
    run_command("python", "-m", "black", *files, verbose=verbose)


linter([".py"], lint=lint_py_files, fix=fix_py_files)
