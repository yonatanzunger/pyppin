import inspect
from typing import (Callable, Mapping, NamedTuple, Optional, Type, TypeVar,
                    Union)

ValueType = TypeVar("ValueType")
KeyType = TypeVar("KeyType")

CacheType = Mapping[KeyType, ValueType]
WrappedFunctionType = Callable[..., ValueType]

# TODO LET'S MAKE THIS NICER
# - Cache exceptions
# - Syntax
# @memoize(cls=dict, key=lambda x, y: y)
# @memoize(var='cache', ...)
# @memoize(cls=TTLCache, maxsize=13)


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


def memoize(
    cache: Optional[Union[CacheType, Type[CacheType], str]] = dict,
    key: Optional[Callable[..., KeyType]] = None,
) -> Callable[[WrappedFunctionType], WrappedFunctionType]:
    def wrapper(function: WrappedFunctionType) -> WrappedFunctionType:
        # Set up a function that takes the arguments passed to the function and returns the actual
        # cache object we're going to use. We do this in the wrapper so that we aren't doing
        # expensive logic at call time!
        getCache: Callable[..., CacheType]

        if isinstance(cache, str):
            # TODO: It would be nice to verify in this case that we're in a method declaration, but
            # there's not really any way to do that.
            def getCache(*args, **kwargs) -> CacheType:
                assert args
                return getattr(args[0], cache)

        elif isinstance(cache, type):
            # If you passed a type, we'll create a unique static object of this type.
            realCache = cache()

            def getCache(*args, **kwargs) -> CacheType:
                return realCache

        else:
            # You passed the cache itself.
            def getCache(*args, **kwargs) -> CacheType:
                return cache

        # Set up the key-fetching function with reasonable defaults. Again, it would be nice if we
        # could explicitly detect that we're decorating a method, but there's no good way to do
        # that. (The closest approximation would involve examining the stack, and even that's messy
        # because __build_class__ is a hidden function and we could only detect its presence
        # implicitly)
        nonlocal key
        if key is None:
            signature = inspect.signature(function)
            if len(signature.parameters) == 1:

                def defaultCacheKeyForFunction(*args, **kwargs):
                    return args[0]

                key = defaultCacheKeyForFunction

            elif len(signature.parameters) == 2 and next(
                iter(signature.parameters)
            ) in ("self", "cls"):

                def defaultCacheKeyForMethod(*args, **kwargs):
                    return args[1]

                key = defaultCacheKeyForMethod

            if key is None:
                raise AssertionError(
                    f"A default cache key signature could not be inferred for "
                    f"'{function.__name__}', which has call signature {signature}. "
                    f"Please explicitly specify a value for key in the @memoize "
                    f"decorator."
                )

        def wrapped(*args, _skip: CacheSkipArgument = None, **kwargs) -> ValueType:
            cacheFlags = CacheFlags.fromSkipArg(_skip)
            # Fast path if we're skipping cache completely.
            if not cacheFlags.read and not cacheFlags.write:
                return function(*args, **kwargs)

            cache = getCache(*args)
            cacheKey = key(*args, **kwargs)

            if cacheFlags.read:
                try:
                    # Cache hit!
                    return cache[cacheKey]
                except KeyError:
                    pass

            value = function(*args, **kwargs)

            if cacheFlags.write:
                cache[cacheKey] = value

            return value

        return wrapped

    return wrapper
