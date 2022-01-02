"""A function to import an entire directory; useful with registered classes!"""

import importlib.machinery
import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Dict, List, Optional, Union

from pyppin.list_files import list_files

DEFAULT_EXCLUDE = [
    # Ignore dotfiles, and more importantly, dot directories.
    "\\..*",

    # Don't try to recurse into the Python build cache.
    "__pycache__",

    # Don't import underscore files; they're not part of the API of a directory.
    "_.*",
]


def bulk_import(
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

    Returns:
        A dict of all the modules found.

    Example: If you have the structure::

        impls/
            class1.py
            class2.py
            foo/
                class3.py

    then `bulk_import('impls')` would create the modules `class1`, `class2`, and `foo.class3`,
    while `bulk_import(Path('impls'), root=Path('impls').parent)` would instead load the same
    files as `impls.class1`, `impls.class2`, and `impls.foo.class3`.
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

    for file in list_files(
        path,
        recursive=recursive,
        select=lambda p: not any(pat.match(p.name) for pat in pats),
    ):
        # The set of file types that can actually be imported.
        if file.suffix not in importlib.machinery.all_suffixes():
            continue

        # Make the name we're going to give this module.
        relpath = file.relative_to(root).with_suffix("")
        name = ".".join(relpath.parts)

        # Don't re-import things.
        if name in sys.modules:
            if verbose:
                print(f"Not importing {name} from {file}: Already loaded.")
            found[name] = sys.modules[name]
            continue

        if verbose:
            print(f"Importing {name} from {file}")

        # cf the documentation of importlib: it's important to insert the module into sys.modules
        # *before* trying to exec its contents, but you need to clean that up afterwards!
        spec = importlib.util.spec_from_file_location(name, file)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        found[name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            del sys.modules[name]
            del found[name]
            raise ImportError(f"While importing {file}: {e}") from e

    return found
