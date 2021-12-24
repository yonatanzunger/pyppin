from typing import List

from _metalint import linter, runCommand


def lintPyFiles(files: List[str], verbose: bool) -> bool:
    if not files:
        return True

    ok = True
    if not runCommand("python", "-m", "flake8", *files, verbose=verbose):
        ok = False
    if not runCommand(
        "python", "-m", "isort", "--atomic", "--check-only", *files, verbose=verbose
    ):
        ok = False
    if not runCommand("python", "-m", "black", "--check", *files, verbose=verbose):
        ok = False
    if not runCommand("python", "-m", "mypy", *files, verbose=verbose):
        ok = False

    print(f'Lint of {len(files)} Python files {"successful" if ok else "failed"}!')
    return ok


def fixPyFiles(files: List[str], verbose: bool) -> None:
    if not files:
        return

    runCommand("python", "-m", "isort", "--atomic", *files, verbose=verbose)
    runCommand("python", "-m", "black", *files, verbose=verbose)


linter(["py"], lint=lintPyFiles, fix=fixPyFiles)


def lintCppFiles(files: List[str], verbose: bool) -> bool:
    if not files:
        return True

    ok = runCommand("python", "-m", "cpplint", "--quiet", *files, verbose=verbose)
    print(f'Lint of {len(files)} C/C++ files {"successful" if ok else "failed"}!')
    return ok


def fixCppFiles(files: List[str], verbose: bool) -> None:
    if not files:
        return

    return runCommand("clang-format", "-i", "-style=Google", *files, verbose=verbose)


linter(["c", "cpp", "cc", "h", "hpp"], lint=lintCppFiles, fix=fixCppFiles)
