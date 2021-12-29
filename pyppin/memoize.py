import functools
from typing import (Any, Callable, Hashable, Mapping, NamedTuple, Optional,
                    Tuple, Type, TypeVar, Union)

import cachetools.keys

ValueType = TypeVar("ValueType")
KeyType = TypeVar("KeyType")

CacheType = Mapping[KeyType, ValueType]
WrappedFunctionType = Callable[..., ValueType]


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
    cls: Optional[Type[CacheType]] = None,
    var: Optional[str] = None,
    cacheobj: Optional[CacheType] = None,
    key: Optional[Callable[..., KeyType]] = None,
    cacheExceptions: bool = False,
    **kwargs,
) -> Callable[[WrappedFunctionType], "_WrappedDescriptor"]:
    """A decorator to memoize (cache) the results of a class or instance method.

    Args:
        cls: If given, create a separate cache for just this function, of the selected type. Any
            **kwargs given will be passed to the constructor for this object. This is the most
            common way to select a cache; some good examples are dict, any of the classes from
            cachetools, or weakred.WeakValueDictionary.
        var: If given, this is the name of a class/instance variable (presumably set up elsewhere)
            to use as the cache. This allows you to share a single cache across multiple methods;
            just make sure to use distinct keys!
        cacheobj: An existing object to use as a cache. Note that this option is a bit hidden
            because something like 'cacheobj={}' in an instance method decorator will *not* do
            what you intend! (That would create a per-*class* cache and use it for every instance)

    If none of the cache selector args (cls, var, cacheobj) are given, the default is cls=dict.

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
        core = _CacheCore(
            function=function,
            cls=cls,
            var=var,
            cacheobj=cacheobj,
            key=key or _defaultMethodCacheKey,
            cacheExceptions=cacheExceptions,
            **kwargs,
        )

        return _WrappedDescriptor(core)

    return wrapper


def cache(
    cls: Optional[Type[CacheType]] = None,
    cacheobj: Optional[CacheType] = None,
    key: Optional[Callable[..., KeyType]] = None,
    cacheExceptions: bool = False,
    **kwargs,
) -> Callable[[WrappedFunctionType], "_CacheCore"]:
    """A decorator to memoize (cache) the results of a function call.

    See the documentation for @cachemethod. The 'var' argument isn't available here, for obvious
    reasons.
    """

    def wrapper(function: WrappedFunctionType) -> _CacheCore:
        return _CacheCore(
            function=function,
            cls=cls,
            cacheobj=cacheobj,
            key=key or _defaultFunctionCacheKey,
            cacheExceptions=cacheExceptions,
            **kwargs,
        )

    return wrapper


##################################################################################################
# Implementation begins here.


class _CacheCore(object):
    def __init__(
        self,
        function: WrappedFunctionType,
        key: Callable[..., KeyType],
        cacheExceptions: bool,
        cls: Optional[Type[CacheType]] = None,
        var: Optional[str] = None,
        cacheobj: Optional[CacheType] = None,
        **kwargs,
    ) -> None:
        countArgs = (
            (1 if cls is not None else 0)
            + (1 if var is not None else 0)
            + (1 if cacheobj is not None else 0)
        )

        if countArgs > 1:
            raise AssertionError(
                "No more than one of cls, var, and cacheobj can be given for a @memoize decorator"
            )
        elif countArgs == 0:
            cls = dict

        # self.cache will be a function that goes from the passed arguments to the actual cache
        # object. We need these arguments for the case where the cache was specified as an instance
        # variable name, so we have to getattr on args[0].

        getCache: Callable[..., CacheType]
        if var:

            def getCache(*args, **kwargs) -> CacheType:
                assert args
                return getattr(args[0], var)

        elif cls:
            # If you passed a type, we'll create a unique static object of this type.
            realCache = cls(**kwargs)

            def getCache(*args, **kwargs) -> CacheType:
                return realCache

        else:
            # You passed the cache itself.
            assert cacheobj is not None

            def getCache(*args, **kwargs) -> CacheType:
                return cacheobj

        self.cache = getCache
        self.key = key
        self.function = function
        self.cacheExceptions = cacheExceptions

        functools.update_wrapper(self, function)

    def getCacheAndKey(self, *args, **kwargs) -> Tuple[CacheType, KeyType]:
        return (self.cache(*args), self.key(*args, **kwargs))

    def invoke(self, skip: CacheSkipArgument, *args, **kwargs) -> ValueType:
        """The inner meat of a memoized function, the actual wrapped function!"""
        cacheFlags = CacheFlags.fromSkipArg(skip)
        # Fast path if we're skipping cache completely.
        if not cacheFlags.read and not cacheFlags.write:
            return self.function(*args, **kwargs)

        cache, cacheKey = self.getCacheAndKey(*args, **kwargs)

        if cacheFlags.read:
            try:
                # Cache hit!
                result = cache[cacheKey]
            except KeyError:
                pass
            else:
                if self.cacheExceptions and isinstance(result, Exception):
                    raise result
                else:
                    return result

        try:
            value = self.function(*args, **kwargs)
        except Exception as e:
            if self.cacheExceptions and cacheFlags.write:
                # Drop the traceback to avoid holding pointers to a stack trace in a cache.
                cache[cacheKey] = e.with_traceback(None)
            raise

        if cacheFlags.write:
            cache[cacheKey] = value

        return value

    def incache(self, *args, **kwargs) -> bool:
        cache, cacheKey = self.getCacheAndKey(*args, **kwargs)
        try:
            cache[cacheKey]
        except KeyError:
            return False
        else:
            return True


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


def _defaultMethodCacheKey(self, *args, **kwargs) -> Hashable:
    """The default cache key function we use for instance/class methods. Note that we treat "self"
    as an argument here, and pass it differently to the underlying cache function!
    """
    return _defaultFunctionCacheKey(id(self), *args, **kwargs)


_defaultFunctionCacheKey = cachetools.keys.typedkey
