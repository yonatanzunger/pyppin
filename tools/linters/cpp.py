from typing import List

from tools.linters.common import linter, runCommand


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


linter([".c", ".cpp", ".cc", ".h", ".hpp"], lint=lintCppFiles, fix=fixCppFiles)
