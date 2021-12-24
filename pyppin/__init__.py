from typing import TypeVar, Optional


_T = TypeVar("_T")


def assertNotNone(val: Optional[_T]) -> _T:
    assert val is not None
    return val
