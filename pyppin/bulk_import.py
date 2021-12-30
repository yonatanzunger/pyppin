import importlib.machinery
from types import ModuleType
import importlib.util
import re
import sys
from pathlib import Path
from typing import List, Optional, Union, Dict

from pyppin.list_files import listFiles

DEFAULT_EXCLUDE = [
    "\\..*",
    "__pycache__",
]


def bulkImport(
    path: Union[str, Path],
    recursive: bool = True,
    exclude: List[str] = DEFAULT_EXCLUDE,
    verbose: bool = False,
    root: Optional[Union[str, Path]] = None,
) -> Dict[str, ModuleType]:
    """Import all Python files in a given directory.

    This is useful if, for example, a directory contains implementations which are registered
    through some mechanism that lets them be accessed programmatically! For an example of this,
    look at the implementation of tools/lint.py in the pyppin package itself.

    Args:
        path: The file or directory path from which to start the import.
        recursive: If true, recurse into directories.
        exclude: A list of filename regexps (not globs!) to skip.
        verbose: If true, print when we import things.
        root: If given, modules will be named as dotted components starting from this
            path. By default, it is the same as path.

    Returns: A dict of all the modules found.

    Example: If you have the structure

        impls/
            class1.py
            class2.py
            foo/
                class3.py

    then bulkImport('impls') would create the modules class1, class2, and foo.class3, while
    bulkImport(Path('impls'), root=Path('impls').parent) would instead load the same files
    as impls.class1, impls.class2, and impls.foo.class3.
    """
    if isinstance(path, str):
        path = Path(path)

    if isinstance(root, str):
        root = Path(root)
    elif root is None:
        root = path

    assert path.is_relative_to(root)

    found: Dict[str, ModuleType] = {}

    pats = [re.compile(p) for p in exclude]

    for file in listFiles(
        path,
        recursive=recursive,
        select=lambda p: not any(pat.match(p.name) for pat in pats),
    ):
        if file.suffix not in importlib.machinery.all_suffixes():
            continue

        # Make the name we're going to give this module.
        relpath = file.relative_to(root).with_suffix("")
        name = ".".join(relpath.parts)

        if name in sys.modules:
            if verbose:
                print(f"Not importing {name} from {file}: Already loaded.")
            found[name] = sys.modules[name]
            continue

        if verbose:
            print(f"Importing {name} from {file}")

        spec = importlib.util.spec_from_file_location(name, file)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        found[name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            del sys.modules[name]
            del found[name]
            raise ImportError(f"While importing {file}: {e}")

    return found
