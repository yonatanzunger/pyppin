"""A function to import a Python file from its pathname."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Optional, Union

from pyppin.base import assert_not_none


def import_file(
    filename: Union[str, Path], name: Optional[str] = None, reimport: bool = False
) -> ModuleType:
    """Import a single Python file.

    Unlike the methods in importlib, this takes an honest-to-Cthulhu *pathname* as its argument.

    WARNING: This will actually exec the file in question, just like importing it would. Do not call
    this on untrusted data for hopefully obvious reasons.

    Args:
        filename: The file to import.
        name: The name of the module to create. If not given, this will default to the name of
            the file.
        reimport: If the name is already imported, and this is true, we'll try to reimport it.
            That said, this is a fragile operation, because any symbols being actively referenced
            from the already-imported file are going to still be there; that is, it has all the same
            caveats as importlib.reload.

    Returns: The newly-imported module.
    """
    if isinstance(filename, str):
        filename = Path(filename)

    name = name or filename.stem

    # Per the importlib documentation, it's important to insert the module into sys.modules *before*
    # trying to exec its contents -- but if exec goes wrong, that means we need to back that out.
    preserved: Optional[ModuleType] = sys.modules.get(name, None)

    if preserved is not None and not reimport:
        return preserved

    spec = assert_not_none(importlib.util.spec_from_file_location(name, filename))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module

    try:
        assert_not_none(spec.loader).exec_module(module)
    except Exception as e:
        if preserved is not None:
            sys.modules[name] = preserved
        else:
            del sys.modules[name]
        raise ImportError(f"Failed to import {filename} as {name}") from e

    return module
