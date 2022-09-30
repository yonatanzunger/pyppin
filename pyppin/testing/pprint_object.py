"""Pretty-print the contents of an object, including all its Python innards, for debugging."""

from pprint import pprint
from typing import IO, Any, Dict, Iterable, Optional, Set


def pprint_object(
    thing: Any,
    file: Optional[IO[str]] = None,
    recurse_into: Optional[Iterable[str]] = None,
) -> None:
    """Pretty-print all the innards of an object.

    Unlike pprint(thing), this will print everything in the objects dir, including __items__.
    This is basically for debugging.

    Args:
        thing: What to print
        file: Where to print it (default stdout)
        recurse_into: Any variable names listed here will be expanded recursively.
    """
    recurse: Set[str]
    if isinstance(recurse_into, str):
        recurse = {recurse_into}
    elif recurse_into is not None:
        recurse = set(recurse_into)
    else:
        recurse = set()
    pprint(_as_dict(thing, recurse), stream=file)


def _as_dict(thing: Any, recurse: Set[str]) -> Dict[str, Any]:
    return {
        attr: _as_dict(getattr(thing, attr), recurse)
        if attr in recurse
        else getattr(thing, attr)
        for attr in dir(thing)
    }
