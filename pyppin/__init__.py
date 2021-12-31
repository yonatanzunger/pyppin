from typing import TypeVar, Optional


_T = TypeVar("_T")


def assert_not_none(val: Optional[_T]) -> _T:
    assert val is not None
    return val
