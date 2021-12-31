from typing import List

from tools.linters.common import linter, run_command


def lint_cpp_files(files: List[str], verbose: bool) -> bool:
    if not files:
        return True

    ok = run_command("python", "-m", "cpplint", "--quiet", *files, verbose=verbose)
    print(f'Lint of {len(files)} C/C++ files {"successful" if ok else "failed"}!')
    return ok


def fix_cpp_files(files: List[str], verbose: bool) -> None:
    if not files:
        return

    return run_command("clang-format", "-i", "-style=Google", *files, verbose=verbose)


linter([".c", ".cpp", ".cc", ".h", ".hpp"], lint=lint_cpp_files, fix=fix_cpp_files)
