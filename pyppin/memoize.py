import functools
import threading
from contextlib import AbstractContextManager, nullcontext
from typing import (
    Any,
    Callable,
    Hashable,
    Mapping,
    NamedTuple,
    Optional,
    Type,
    TypeVar,
    Union,
)

import cachetools.keys

ValueType = TypeVar("ValueType")
KeyType = TypeVar("KeyType")

CacheType = Mapping[KeyType, ValueType]
WrappedFunctionType = Callable[..., ValueType]

# The types you can pass in order to select the cache and its lock when decorating a method or a
# bare function, respectively.
MethodCacheSelector = Union[CacheType, Type[CacheType], str, None]
MethodLockSelector = Union[
    AbstractContextManager, Type[AbstractContextManager], bool, str
]
FunctionCacheSelector = Union[CacheType, Type[CacheType], None]
FunctionLockSelector = Union[AbstractContextManager, Type[AbstractContextManager], bool]


class CacheFlags(NamedTuple):
    """These flags indicate how the cache should be consulted on a given call."""

    # If read is true, we should see if the value is in the cache before the function call, and if
    # so, return the cached value. Setting it to false means we ignore the cached value.
    read: bool

    # If write is true, then if we didn't get the value from the cache (either because read=False
    # or because of a cache miss), we should update the cache with the new value.
    write: bool

    @classmethod
    def fromSkipArg(cls, arg: Union[bool, str, "CacheFlags", None]) -> "CacheFlags":
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


SKIP_CACHE = CacheFlags(read=False, write=False)
USE_CACHE = CacheFlags(read=True, write=True)


# This is the type for a "cache skip" argument. Any @memoized function or method will have an
# optional kwarg _skip of this type attached, which you can use to control how the cache is invoked.
CacheSkipArgument = Union[bool, str, CacheFlags, None]


def cachemethod(
    cache: MethodCacheSelector = dict,
    lock: MethodLockSelector = False,
    key: Optional[Callable[..., KeyType]] = None,
    cacheExceptions: bool = False,
    **kwargs,
) -> Callable[[WrappedFunctionType], "_WrappedDescriptor"]:
    """A decorator to memoize (cache) the results of a class or instance method.

    For ordinary functions, use @cache (below) instead.

    Args:
        cache: The cache to use for this method. Valid values are:
            * A class (such as dict, weakref.WeakValueDictionary, or any of the cache classes
              from cachetools); create a separate cache of this type for just this method. Any
              **kwargs passed to @cachemethod will be forwarded on to the cache's constructor.
            * The (string) name of an instance variable of the class whose method is being
              decorated; this variable should usually be set up in the object __init__ method.
            * An explicit object to use as a cache. (Careful! @cachemethod(cache={}) will create
              a per-*class* dict and use it for every *instance*, which is rarely what you want!)
            * None to simply not cache.
        lock: The mutex to use to guard the cache. Valid values are:
            * A class (such as threading.Lock) to use for the lock.
            * The (string) name of an instance variable containing the lock.
            * An explicit lock object (typically a threading.Lock).
            * True (equivalent to the class threading.Lock, the most common value to pass)
            * False (to not lock the cache)

    The default behavior is cache=dict, lock=False, which uses a dedicated unlocked dict to cache
    the method.

        key: A function that takes the same arguments as the decorated function, and returns
            a cache key to use for those values. If not given, @memoize will pick a default based
            on hashing the passed arguments, and using the id() of the instance.

        cacheExceptions: If True and the function raises an exception, we will cache the
            *exception*, so that future calls to the function will get a cache hit and the response
            to that hit will be to re-raise the exception.

    The resulting function will be a wrapped version of the original, but will have an additional
    keyword argument _skip: Union[bool, str, CacheFlags, None]=None, which can be used to control
    caching behavior when invoking it. Some particular useful arguments:

        wrappedfn(_skip=True) will completely skip the cache.
        wrappedfn(_skip='r') will always re-evaluate the function, and update the cache, so
            this can be used to forcibly refresh the cache entry for these arguments.
        wrappedfn(_skip='w') will check, but not update, the cache; this is good if it's a
            value that would be expensive to store in cache, or otherwise a scenario where
            updating the cache would be bad. (e.g., if there are two paths that hit a function,
            one of which is performance-critical and the other isn't, and the second would have
            very different key distributions, you can pass this for the non-critical one so it
            will get the benefits of the cache when possible, but not pollute the cache for the
            first one)

    In addition, the wrapped function has an incache() method (i.e., foo.wrappedfn.incache(...))
    that has the same signature as the function itself, but returns a bool: True if the given
    arguments would lead to a cache hit, False otherwise.
    """

    def wrapper(function: WrappedFunctionType) -> _WrappedDescriptor:
        # Our wrapper function will return a non-data descriptor whose __get__ returns a callable
        # object, rather than a function. This way, when you invoke __get__ on it, it can capture
        # the thing on which the descriptor is being called (self or the class or whatever) and
        # curry that as a "zeroth argument" for all the underlying function calls. NB that Python
        # would do this automatically if we just returned a function, but then we couldn't implement
        # things like incache()!
        return _WrappedDescriptor(
            _CacheCore(
                function=function,
                cache=cache,
                lock=lock,
                key=key or _defaultMethodCacheKey,
                cacheExceptions=cacheExceptions,
                **kwargs,
            )
        )

    return wrapper


def cache(
    cache: FunctionCacheSelector = dict,
    lock: FunctionLockSelector = False,
    key: Optional[Callable[..., KeyType]] = None,
    cacheExceptions: bool = False,
    **kwargs,
) -> Callable[[WrappedFunctionType], "_WrappedFunction"]:
    """A decorator to memoize (cache) the results of a function call.

    See the documentation for @cachemethod. The 'var' argument isn't available here, for obvious
    reasons.
    """

    def wrapper(function: WrappedFunctionType) -> _WrappedFunction:
        return _WrappedFunction(
            _CacheCore(
                function=function,
                cache=cache,
                lock=lock,
                key=key or _defaultFunctionCacheKey,
                cacheExceptions=cacheExceptions,
                **kwargs,
            )
        )

    return wrapper


##################################################################################################
# Implementation begins here.


class _CacheState(NamedTuple):
    # All the cache-related stuff for a single operation.
    cache: CacheType
    lock: AbstractContextManager
    key: KeyType

    def get(self) -> ValueType:
        # Either return the value or raise a KeyError
        with self.lock:
            return self.cache[self.key]

    def set(self, value: ValueType) -> None:
        with self.lock:
            self.cache[self.key] = value


class _CacheCore(object):
    def __init__(
        self,
        function: WrappedFunctionType,
        cache: MethodCacheSelector,
        lock: MethodLockSelector,
        key: Callable[..., KeyType],
        cacheExceptions: bool,
        **kwargs,
    ) -> None:
        # self.cache will be a function that goes from the passed arguments to the actual cache
        # object. We need these arguments for the case where the cache was specified as an instance
        # variable name, so we have to getattr on args[0].
        self.cache: Callable[..., CacheType]
        if isinstance(cache, str):
            self.cache = _attributeGetter(cache)
        elif isinstance(cache, type):
            self.cache = _constantGetter(cache(**kwargs))
        else:
            self.cache = _constantGetter(cache)

        # Same drill for self.lock.
        self.lock: Callable[..., AbstractContextManager]

        if isinstance(lock, str):
            self.lock = _attributeGetter(lock)
        elif isinstance(lock, type):
            self.lock = _constantGetter(lock())
        elif isinstance(lock, bool):
            self.lock = _constantGetter(threading.Lock() if lock else nullcontext())
        else:
            self.lock = _constantGetter(lock)

        self.key = key
        self.function = function
        self.cacheExceptions = cacheExceptions

        functools.update_wrapper(self, function)

    def getCacheState(self, *args, **kwargs) -> Optional[_CacheState]:
        cache = self.cache(*args, **kwargs)
        return (
            _CacheState(
                cache=cache,
                lock=self.lock(*args, **kwargs),
                key=self.key(*args, **kwargs),
            )
            if cache is not None
            else None
        )

    def invoke(self, skip: CacheSkipArgument, *args, **kwargs) -> ValueType:
        """The inner meat of a memoized function, the actual wrapped function!"""
        cacheFlags = CacheFlags.fromSkipArg(skip)
        # Fast path if we're skipping cache completely.
        if not cacheFlags.read and not cacheFlags.write:
            return self.function(*args, **kwargs)

        cache = self.getCacheState(*args, **kwargs)
        # Fast path if there's no cache.
        if not cache:
            return self.function(*args, **kwargs)

        # Read
        if cacheFlags.read:
            try:
                result = cache.get()
            except KeyError:
                pass
            else:
                # Cache hit! Return or raise the result, as appropriate.
                if self.cacheExceptions and isinstance(result, Exception):
                    raise result
                else:
                    return result

        # Handle cache misses
        try:
            value = self.function(*args, **kwargs)
        except Exception as e:
            if self.cacheExceptions and cacheFlags.write:
                # Drop the traceback to avoid holding pointers to a stack trace in a cache.
                cache.set(e.with_traceback(None))
            raise

        # Write
        if cacheFlags.write:
            cache.set(value)

        return value

    def incache(self, *args, **kwargs) -> bool:
        try:
            self.getCacheState(*args, **kwargs).get()
        except (KeyError, AttributeError):
            return False
        else:
            return True


# Two helper functions that return named attributes of args[0] (ie self) or just fixed values.


def _attributeGetter(name: str) -> Callable:
    def getAttribute(*args, **kwargs) -> Any:
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

    return getAttribute


def _constantGetter(value: Any) -> Callable:
    def getConstant(*args, **kwargs) -> Any:
        return value

    return getConstant


class _WrappedMethod(object):
    def __init__(
        self,
        core: _CacheCore,
        instance: Any,
    ) -> None:
        self.core = core
        self.instance = instance

    def __call__(self, *args, _skip: CacheSkipArgument = None, **kwargs) -> ValueType:
        # Note how we curry self.wrappedSelf as a fake "argument zero," just like if this were a
        # true instance method. We do this manually (rather than having Python do it) so that
        # WrappedMethod can implement more than just __call__ -- the built-in trick only works
        # for instance methods, not arbitrary callables.
        return self.core.invoke(_skip, self.instance, *args, **kwargs)

    def incache(self, *args, **kwargs) -> bool:
        return self.core.incache(self.instance, *args, **kwargs)


class _WrappedDescriptor(object):
    def __init__(self, core: _CacheCore) -> None:
        self.core = core

    def __get__(self, instance: Any, owner: Any = None) -> _WrappedMethod:
        return _WrappedMethod(self.core, instance or owner)


class _WrappedFunction(object):
    def __init__(self, core: _CacheCore) -> None:
        self.core = core

    def __call__(self, *args, _skip: CacheSkipArgument = None, **kwargs) -> ValueType:
        return self.core.invoke(_skip, *args, **kwargs)

    def incache(self, *args, **kwargs) -> bool:
        return self.core.incache(*args, **kwargs)


def _defaultMethodCacheKey(self, *args, **kwargs) -> Hashable:
    """The default cache key function we use for instance/class methods. Note that we treat "self"
    as an argument here, and pass it differently to the underlying cache function!
    """
    return _defaultFunctionCacheKey(id(self), *args, **kwargs)


_defaultFunctionCacheKey = cachetools.keys.typedkey
