"""Caching decorators for functions and methods

This file provides two decorators, `@cache` (for functions) and `@cachemethod` (for methods),
which can be used to memoize the return values of the function. For example::

    class MyClass(object):
        @cachemethod(key=lambda self, val1, val2: val1)
        def mymethod(self, val1: string, val2: int) -> bool:
            ....

will cause ``mymethod`` to automatically cache its results in a dedicated dict, keyed only by
``val1`` -- that is, calls with different values of ``val2`` will be assumed to always yield the
same result.

The decorators share most of their arguments and behavior:

    **cache:** The cache to use for this method. Valid values are:

        * A class (such as ``dict``, ``weakref.WeakValueDictionary``, or any of the cache classes
          from ``cachetools``); create a separate cache of this type for just this method. Any
          ``**kwargs`` passed to the decorator will be forwarded on to the cache's constructor.
        * An explicit object to use as a cache. (Careful! ``@cachemethod(cache={})`` will
          create a per-*class* dict and use it for every *instance*, which is rarely what
          you want!)
        * ``None`` to simply not cache.
        * (``@cachemethod`` only) The (string) name of an instance variable of the class whose
          method is being decorated; this variable should usually be set up in the object
          ``__init__`` method.

        The default is dict, i.e. to use a per-method unbounded cache.

    **lock:** The mutex to use to guard the cache. Valid values are:

        * A class (such as threading.Lock) to use for the lock.
        * An explicit lock object (typically a threading.Lock).
        * True (equivalent to the class threading.Lock, the most common value to pass)
        * False (to not lock the cache)
        * ``@cachemethod`` only: The (string) name of an instance variable containing the lock.

        The default is False, i.e. to not lock the cache.

    **key:** A function that maps the decorated function's argument to the cache key.

        This function should take the same arguments (including ``self`` if appropriate) as the
        decorated function or method, and returns a cache key to use given those values. The default
        is to infer a key function based on all function arguments and the id of self. Note that
        this default only works if all the arguments are hashable, and calls will raise
        ``ExplicitKeyNeeded`` if this is not true; you will very often want to override this
        default!

    **cache_exceptions:** Whether exceptions raised by the function should also be cached.

        If True and the function raises an exception, we will cache the *exception*, so that
        future calls to the function will get a cache hit and the response to that hit will
        be to re-raise the exception. The default is not to do this.

Skipping the Cache
==================

The resulting function will be a wrapped version of the original, but will have an additional
keyword argument ``_skip: Union[bool, str, CacheFlags, None]=None``, which can be used to control
caching behavior when invoking it. Some particular useful arguments:

* ``wrappedfn(..., _skip=True)`` will completely skip the cache.
* ``wrappedfn(..., _skip='r')`` ("skip the cache read") will always re-evaluate the underlying
function, and update the cache, so this can be used to forcibly refresh the cache entry for these
arguments.
* ``wrappedfn(..., _skip='w')`` ("skip the cache write") will check the cache and use its value on a
hit, and on a cache miss will re-evaluate the function but *not* update the cache. There are two big
cases where this is helpful: if it's a value that would be expensive to store in the cache, or if
you're doing an "unusual operation" which you know isn't going to get cache hits in the future, and
writing it could pollute the cache. (For example, if there are two paths that hit a function, one of
which is performance-critical and the other not, and the second would have a very different
distribution of keys, then skipping the cache write for the non-critical operation guarantees that
it won't mess up the cache for the critical one.)

Checking cache presence
=======================

In addition, the wrapped function has an incache() method of its own:

* ``wrappedfn.incache(...)`` has the same signature as the function itself, but returns a bool:
  True if the given arguments would lead to a cache hit, False otherwise.
"""

import functools
import threading
from contextlib import AbstractContextManager, nullcontext
from typing import (
    Any,
    Callable,
    Generic,
    Hashable,
    MutableMapping,
    NamedTuple,
    Optional,
    Type,
    TypeVar,
    Union,
)

from pyppin.base.flex_decorator import flex_decorator

ValueType = TypeVar("ValueType")
KeyType = TypeVar("KeyType")

CacheType = MutableMapping[KeyType, ValueType]
WrappedFunctionType = Callable[..., ValueType]

# The types you can pass in order to select the cache and its lock when decorating a method or a
# bare function, respectively.
MethodCacheArgument = Union[CacheType, Type[CacheType], str, None]
MethodLockArgument = Union[
    AbstractContextManager, Type[AbstractContextManager], bool, str
]
FunctionCacheArgument = Union[CacheType, Type[CacheType], None]
FunctionLockArgument = Union[AbstractContextManager, Type[AbstractContextManager], bool]


class CacheFlags(NamedTuple):
    """These flags indicate how the cache should be consulted on a given call."""

    read: bool
    """If read is true, we should see if the value is in the cache before the function call,
    and if so, return the cached value. Setting it to false means we ignore the cached value.
    """

    write: bool
    """If write is true, then if we didn't get the value from the cache (either because
    `read=False` or because of a cache miss), we should update the cache with the new value.
    """

    @classmethod
    def from_skip_arg(cls, arg: "CacheSkipArgument") -> "CacheFlags":
        """Parse a "skip=<foo>" argument into CacheFlags."""
        if arg is None:
            return USE_CACHE
        elif isinstance(arg, CacheFlags):
            return arg
        elif isinstance(arg, bool):
            return SKIP_CACHE if arg else USE_CACHE
        elif isinstance(arg, str):
            read = True
            write = True
            for char in arg:
                lower = char.lower()
                if lower == "r":
                    read = False
                elif lower == "w":
                    write = False
                else:
                    raise ValueError(
                        f'Unexpected character "{char}" in cache skip argument'
                    )
            return CacheFlags(read=read, write=write)
        else:
            raise TypeError(f'Bogus cache skip argument "{arg}"')


SKIP_CACHE = CacheFlags(read=False, write=False)
USE_CACHE = CacheFlags(read=True, write=True)


# This is the type for a "cache skip" argument. Any @memoized function or method will have an
# optional kwarg _skip of this type attached, which you can use to control how the cache is invoked.
CacheSkipArgument = Union[bool, str, CacheFlags, None]


class ExplicitKeyNeeded(Exception):
    """Error: You used the default `key` argument in a place where it doesn't work."""

    pass


@flex_decorator
def cachemethod(
    function: WrappedFunctionType,
    *,
    cache: MethodCacheArgument = dict,
    lock: MethodLockArgument = False,
    key: Optional[Callable[..., KeyType]] = None,
    cache_exceptions: bool = False,
    **kwargs: Any,
) -> "_WrappedDescriptor":
    """A decorator to memoize (cache) the results of a class or instance method.

    See the module documentation for an explanation of its arguments.
    """

    # Our wrapper function will return a non-data descriptor whose __get__ returns a callable
    # object, rather than a function. This way, when you invoke __get__ on it, it can capture
    # the thing on which the descriptor is being called (self or the class or whatever) and
    # curry that as a "zeroth argument" for all the underlying function calls. NB that Python
    # would do this automatically if we just returned a function, but then we couldn't implement
    # things like incache()! (That mechanism doesn't work for other callables; cf the discussion
    # of instance methods in https://docs.python.org/3/reference/datamodel.html)
    return _WrappedDescriptor(
        _CacheCore(
            function=function,
            cache=cache,
            lock=lock,
            key=key or _default_method_cache_key,
            cache_exceptions=cache_exceptions,
            **kwargs,
        )
    )


@flex_decorator
def cache(
    function: WrappedFunctionType,
    *,
    cache: FunctionCacheArgument = dict,
    lock: FunctionLockArgument = False,
    key: Optional[Callable[..., KeyType]] = None,
    cache_exceptions: bool = False,
    **kwargs: Any,
) -> "_WrappedFunction":
    """A decorator to memoize (cache) the results of a function call.

    See the module documentation for an explanation of its arguments.
    """

    return _WrappedFunction(
        _CacheCore(
            function=function,
            cache=cache,
            lock=lock,
            key=key or _default_function_cache_key,
            cache_exceptions=cache_exceptions,
            **kwargs,
        )
    )


##################################################################################################
# Implementation begins here.


# All the cache-related stuff for a single operation.
class _CacheState(Generic[KeyType, ValueType]):
    def __init__(
        self,
        cache: CacheType[KeyType, ValueType],
        lock: AbstractContextManager,
        key: KeyType,
    ) -> None:
        self.cache = cache
        self.lock = lock
        self.key = key

    def get(self) -> ValueType:
        # Either return the value or raise a KeyError
        with self.lock:
            return self.cache[self.key]

    def set(self, value: ValueType) -> None:
        with self.lock:
            self.cache[self.key] = value


class _CacheCore(Generic[KeyType, ValueType]):
    def __init__(
        self,
        function: WrappedFunctionType,
        cache: MethodCacheArgument,
        lock: MethodLockArgument,
        key: Callable[..., KeyType],
        cache_exceptions: bool,
        **kwargs: Any,
    ) -> None:
        """This class encapsulates all the logic which is common between methods and functions --
        the actual meat of invoke() and incache().
        """

        # self.cache will be a function that goes from the passed arguments to the actual cache
        # object. We need these arguments for the case where the cache was specified as an instance
        # variable name, so we have to getattr on args[0].
        self.cache: Callable[..., CacheType]
        if isinstance(cache, str):
            self.cache = _attribute_getter(cache)
        elif isinstance(cache, type):
            self.cache = _constant_getter(cache(**kwargs))
        else:
            self.cache = _constant_getter(cache)

        # Same drill for self.lock.
        self.lock: Callable[..., AbstractContextManager]

        if isinstance(lock, str):
            self.lock = _attribute_getter(lock)
        elif isinstance(lock, type):
            self.lock = _constant_getter(lock())
        elif isinstance(lock, bool):
            self.lock = _constant_getter(threading.Lock() if lock else nullcontext())
        else:
            self.lock = _constant_getter(lock)

        self.key = key
        self.function = function
        self.cache_exceptions = cache_exceptions

    def get_cache_state(self, *args: Any, **kwargs: Any) -> Optional[_CacheState]:
        cache = self.cache(*args, **kwargs)
        return (
            _CacheState(
                cache=cache,
                lock=self.lock(*args, **kwargs),
                key=self.key(*args, **kwargs),  # type: ignore
            )
            if cache is not None
            else None
        )

    def invoke(self, skip: CacheSkipArgument, *args: Any, **kwargs: Any) -> ValueType:
        """The inner meat of a memoized function, the actual wrapped function!"""
        cacheFlags = CacheFlags.from_skip_arg(skip)
        # Fast path if we're skipping cache completely.
        if not cacheFlags.read and not cacheFlags.write:
            return self.function(*args, **kwargs)

        cache = self.get_cache_state(*args, **kwargs)
        # Fast path if there's no cache.
        if not cache:
            return self.function(*args, **kwargs)

        # Read
        if cacheFlags.read:
            try:
                result: ValueType = cache.get()
            except KeyError:
                pass
            else:
                # Cache hit! Return or raise the result, as appropriate.
                if self.cache_exceptions and isinstance(result, Exception):
                    raise result
                else:
                    return result

        # Handle cache misses
        try:
            value = self.function(*args, **kwargs)
        except Exception as e:
            if self.cache_exceptions and cacheFlags.write:
                # Drop the traceback to avoid holding pointers to a stack trace in a cache.
                cache.set(e.with_traceback(None))
            raise

        # Write
        if cacheFlags.write:
            cache.set(value)

        return value

    def incache(self, *args: Any, **kwargs: Any) -> bool:
        state = self.get_cache_state(*args, **kwargs)
        if not state:
            return False
        try:
            state.get()
        except KeyError:
            return False
        else:
            return True


# Two helper functions that return named attributes of args[0] (ie self) or just fixed values.


def _attribute_getter(name: str) -> Callable:
    def get_attribute(*args: Any, **kwargs: Any) -> Any:
        try:
            return getattr(args[0], name)
        except IndexError:
            raise AttributeError(
                f'Tried to fetch the attribute "{name}" of self in a bare function; did you '
                f"use the wrong @cache/@cachemethod decorator?"
            )
        except AttributeError:
            selfname = f' "{args[0].__name__}"' if hasattr(args[0], "__name__") else ""
            raise AttributeError(
                f'The {type(args[0])}{selfname} has no attribute "{name}". Did you pass the wrong '
                f"value to @cachemethod or forget to define the variable?"
            )

    return get_attribute


def _constant_getter(value: Any) -> Callable:
    def get_constant(*args: Any, **kwargs: Any) -> Any:
        return value

    return get_constant


class _WrappedMethod(Generic[ValueType]):
    def __init__(
        self,
        core: _CacheCore,
        instance: Any,
    ) -> None:
        """This object is the actual wrapped function that people will call.

        It's almost identical to _WrappedFunction (below), but this one is aware of what 'self'
        is, so that it can pass that argument correctly to both __call__ and incache. That's why
        you can say something like "foo.wrappedfn.incache(arg1, arg2)" and incache will still
        get foo as its zeroth argument, which it needs in order to actually work.
        """
        self.core = core
        self.instance = instance

    def __call__(
        self, *args: Any, _skip: CacheSkipArgument = None, **kwargs: Any
    ) -> ValueType:
        # Note how we curry self.wrappedSelf as a fake "argument zero," just like if this were a
        # true instance method. We do this manually (rather than having Python do it) so that
        # WrappedMethod can implement more than just __call__ -- the built-in trick only works
        # for instance methods, not arbitrary callables.
        return self.core.invoke(_skip, self.instance, *args, **kwargs)

    def incache(self, *args: Any, **kwargs: Any) -> bool:
        return self.core.incache(self.instance, *args, **kwargs)


class _WrappedDescriptor(Generic[ValueType]):
    def __init__(self, core: _CacheCore) -> None:
        """This is the object we return from @cachemethod.

        It's a non-data descriptor, which will then get plugged in to the class whose method we're
        decorating; when you access foo.wrappedfn, it will really return foo.[this
        descriptor].__get__(foo, foo). That lets us capture the actual value of foo, which we can
        pass to the _WrappedMethod and thus into methods like __call__ and incache.
        """
        self.core = core
        functools.update_wrapper(self, core.function)

    def __get__(self, instance: Any, owner: Any = None) -> _WrappedMethod:
        return _WrappedMethod(self.core, instance or owner)


class _WrappedFunction(Generic[ValueType]):
    def __init__(self, core: _CacheCore) -> None:
        """This is the object we return from @cache.

        It's just a callable object that exposes the wrapped function as well as incache.
        """
        self.core = core
        functools.update_wrapper(self, core.function)

    def __call__(
        self, *args: Any, _skip: CacheSkipArgument = None, **kwargs: Any
    ) -> ValueType:
        return self.core.invoke(_skip, *args, **kwargs)

    def incache(self, *args: Any, **kwargs: Any) -> bool:
        return self.core.incache(*args, **kwargs)


def _default_method_cache_key(self: object, *args: Any, **kwargs: Any) -> Hashable:
    """The default cache key function we use for instance/class methods. Note that we treat "self"
    as an argument here, and pass it differently to the underlying cache function!
    """
    return _default_function_cache_key(id(self), *args, **kwargs)


def _default_function_cache_key(*args: Any, **kwargs: Any) -> int:
    try:
        return hash(args + tuple(sorted(kwargs.items())))
    except TypeError:
        raise ExplicitKeyNeeded(
            "The default cache key cannot be used for this function; not all of its arguments "
            "are hashable types. Please specify an explicit key= argument for its caching "
            "decorator."
        )
