"""An instance method decorator to make initializers execute once, on demand."""
from typing import Any, Callable, Generic, Optional, TypeVar

T = TypeVar("T")
PREFIX = "__lazyinit_"


class _LazyInitializedProperty(Generic[T]):
    def __init__(self, name: str, initializer: Callable[[object], T]) -> None:
        self.varname = PREFIX + name
        self.initializer = initializer

    def __get__(self, instance: object, owner: Optional[type] = None) -> T:
        if not hasattr(instance, self.varname):
            setattr(instance, self.varname, self.initializer(instance))
        return getattr(instance, self.varname)

    def __set__(self, instance: object, value: T) -> None:
        setattr(instance, self.varname, value)

    def __delete__(self, instance: object) -> None:
        if hasattr(instance, self.varname):
            delattr(instance, self.varname)


def lazyinit(method: Callable[[Any], T]) -> _LazyInitializedProperty[T]:
    """An instance method decorator to make it lazy-init and execute once.

    The resulting variable behaves like a property, where the function is only invoked once
    and the result memoized.

    Why would you do this? It makes it really easy to write complicated initializers!::

        class MyClass(object):
            @lazyinit
            def fooService(self) -> FooService:
                ... do something complicated to create a FooService

            @lazyinit
            def barService(self) -> BarService:
                # Note how you can use one lazy-init in another. Don't create infinite loops,
                # for obvious reasons.
                return BarService(self.fooService, "bar")


    If you actually need to change the value of the field -- this is very rare and mostly happens
    in unittests -- you can explicitly set it (``quux.fooService = FooService(...)``), or delete the
    attribute (``del quux.fooService``) in order to force it to reinitialize the next time it's
    called.
    """
    return _LazyInitializedProperty(method.__name__, method)


def reset_all(holder: object) -> None:
    """Reset *all* `lazyinit`'ed variables inside a particular object.

    This is almost exclusively useful in unittests, if you need to hard-reset some kind of
    environment variable or something.
    """
    for name in dir(holder):
        # The hasattr check is because if we call this on an instance, any class-level attributes
        # will show up in the dir, but can't (and shouldn't!) be deleted.
        if name.startswith(PREFIX) and hasattr(holder, name):
            delattr(holder, name)
