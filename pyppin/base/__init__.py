"""Basic language extensions."""

from typing import Optional, TypeVar

_T = TypeVar("_T")


def assert_not_none(val: Optional[_T]) -> _T:
    """Assert that a value is not None, to make mypy happy.

    This is useful when a function technically returns an `Optional[Foo]`, but you know for other
    reasons that it's never None. Wrapping the result in this assertion makes that statement
    explicit and thus makes mypy happy as well when you use its result as a `Foo`.
    """
    assert val is not None
    return val
