"""Merge multiple sorted iterators into a single iterator over sorted tuples."""

from typing import (
    Callable,
    Generic,
    Iterable,
    Iterator,
    List,
    Optional,
    Tuple,
    TypeVar,
    Union,
)

ValueType = TypeVar("ValueType")
KeyType = TypeVar("KeyType")
YieldedType = TypeVar("YieldedType")


class ZipSource(Generic[KeyType, ValueType, YieldedType]):
    def __init__(
        self,
        source: Iterable[ValueType],
        key: Optional[Callable[[ValueType], KeyType]] = None,
        value: Optional[Callable[[ValueType], YieldedType]] = None,
        name: Optional[str] = None,
        required: bool = False,
        missing: Optional[Callable[[KeyType], YieldedType]] = None,
        missing_value: Optional[YieldedType] = None,
    ) -> None:
        """A wrapper around an `Iterable` to give per-source options.

        Args:
            source: The underlying iterable.
            key: A function that transforms the raw thing yielded from the iterator into the key
                which should be compared. The iterator must be sorted by key. The default is to
                use the raw value itself as the key.
            value: A function that transforms the raw thing yielded from the iterator into the
                value which should be yielded by the zip_by_key. The default is to use the raw value
                as the output value.
            name: An optional label for this iterator, used to generate nicer error messages.
            required: If set, this iterator is required: skip the entire output if this iterator
                didn't provide a value for the given key.
            missing: If given, call this function (with the key as argument) to generate a synthetic
                default value for keys not present in this iterator.
            missing_value: If neither required nor missing is set, return this value for missing
                keys.

        Only one of `required`, `missing`, and `missing_value` may be given. The default values will
        return `None` as the missing value.
        """
        self.source = source
        self.key = key
        self.value = value
        self.name = name
        self.required = required
        self.missing = missing
        self.missing_value = missing_value

    @classmethod
    def aux(
        cls, value: Callable[[KeyType], YieldedType], name: Optional[str] = None
    ) -> "ZipSource":
        """Return a ZipSource that contains *just* default values; you can use this to add per-key
        annotations to your yielded output easily.

        For example, ``zip_by_key([1, 2, 3, 4, 5], ZipSource.aux(lambda x: x*x), yield_keys=False)``
        will yield (1, 1), (2, 4), (3, 9), (4, 16), and (5, 25); the second value is the "auxiliary
        source."

        Note that auxiliary sources will only yield when *other* iterators are yielding; if you pass
        only auxiliary sources to `zip_by_key()`, you'll get back the empty sequence.
        """
        return ZipSource(source=tuple(), name=name, missing=value)


def zip_by_key(
    *sources: Union[ZipSource, Iterable],
    yield_keys: bool = True,
) -> Iterator[Union[YieldedType, Tuple[YieldedType, ...]]]:
    """Combine N sorted iterators into a single iterator that yields merged tuples.

    In the simplest use, if the sources are N iterators that yield values that are already strictly
    sorted (i.e., if one yields a then b, then a < b), then this function will yield tuples of
    N+1 items, with each entry being (key, val1, val2...), in sorted order. The key is the common
    key for all of the items in the row, and the individual values are the corresponding values from
    each source (if present) or None (if that iterator didn't have a value for this key).

    The fun comes from the extra options you can provide per-source or overall. You can provide
    options for each source by wrapping it in a ZipSource.

    Args:
        sources: The set of N source iterators to scan over. These can either be simple iterators,
            or be wrapped in a `ZipSource` to provide per-iterator options.
        yield_keys: If True, the tuples will have N+1 elements, and the first is the key. If false,
            the tuples will have N elements, and the key will not be separately yielded.

    Raises:
        IndexError if any of the lists is *not* actually sorted in the correct way.
        AssertionError if invalid options were passed for any source.

    Example
    =======

    Say you have two sorted lists that you want to merge::

        l1 = [1, 2, 3, 4, 5]
        l2 = [(2, "two"), (5, "five"), (7, "seven")]

    Then ``zip_by_key(l1, ZipSource(l2, key=lambda x: x[0]))`` will yield::

        (1, 1, None)
        (2, 2, (2, "two"))
        (3, 3, None)
        (4, 4, None)
        (5, 5, (5, "five"))
        (7, None, (7, "seven"))

    What happened here? The first item in each tuple is the key, which is the same for
    everything in that tuple. The remaining items in the tuple are the values of l1 and l2,
    respectively, where None appears whenever an item is missing. (e.g., l2 has no value for the
    key 3)

    Fancier Example
    ===============

    Let's say instead you have::

        squares = [1, 4, 9, 16, 25]

    You want to get, for each  number in l2, its printed name and its square.::

        zip_by_key(
            ZipSource(l1, key=lambda x: int(sqrt(x))),
            ZipSource(l2, key=lambda x: x[0], value=lambda x: x[1], required=True),
        )

    This will yield::

        (2, 4, "two")
        (5, 25, "five")
        (7, None, "seven"))

    What happened here?

    * For l1, the key is the square root of the value, and the (default) value is just the
      element of l1.
    * For l2, the key is the first element of the tuple, the yielded value is the
      second element, and because required=True, all items that don't show up in l2
      are dropped outright.
    * Because l1 *isn't* required, we get one yielded item that has no value for l1!
    """
    # Surprise! We aren't going to use a heap in here. It turns out that this is more efficient if
    # we just do a sequence of linear scans over all the arrays, because we always need to hit all
    # of them anyway and so maintaining the min is easy.
    ptrs: List[_Pointer] = [_Pointer(source) for source in sources]
    # This value keeps the index (within ptrs) of the entry that has the lowest key.
    minkey = -1
    for index, ptr in enumerate(ptrs):
        if ptr.active and (minkey == -1 or ptr.key < ptrs[minkey].key):
            minkey = index

    # The iterators were all empty! Nothing to do here.
    if minkey == -1:
        return

    # An array that we'll reuse.
    result: List[Optional[YieldedType]] = [None] * (
        len(sources) + (1 if yield_keys else 0)
    )

    assert len(result) > 0

    def _set(index: int, value: Optional[YieldedType]) -> None:
        result[index + 1 if yield_keys else index] = value

    while True:
        # Grab the pointer that's currently farthest behind.
        key = ptrs[minkey].key
        # print(f"Loop start: key is {key} from {minkey}")

        # Let's assemble the result for this key! We're going to reuse this array, since the logic
        # below guarantees that we'll either skip the whole output, or fill in every field of the
        # result.
        if yield_keys:
            result[0] = key

        skip = False
        minkey = -1

        for index, ptr in enumerate(ptrs):
            # print(f"{index}: {ptr}")
            # Early exit if we've fallen off any required iterator.
            if ptr.source.required and not ptr.active:
                return

            if ptr.active and ptr.key == key:
                # Match! Add this to the result and increment the pointer.
                _set(index, ptr.result)
                ptr.increment()
                # print(f"  Update {index} to {ptr}")
            elif ptr.source.required:
                # Don't worry about updating result in this case, we aren't going to output.
                skip = True
            elif ptr.source.missing:
                _set(index, ptr.source.missing(key))
            else:
                _set(index, ptr.source.missing_value)

            # And update minkey. NB we do this *after* any calls to increment().
            if ptr.active and (minkey == -1 or ptr.key < ptrs[minkey].key):
                minkey = index

        # print(f"Loop finished: skip {skip} minkey {minkey} yielded {result}")
        if not skip:
            yield tuple(result) if len(result) > 1 else result[0]  # type: ignore

        if minkey == -1:
            # Nothing left! We're done.
            return


class _Pointer(Generic[KeyType, ValueType, YieldedType]):
    def __init__(
        self,
        source: Union[ZipSource, Iterable],
    ) -> None:
        if isinstance(source, ZipSource):
            self.source = source
            if (
                (1 if source.required else 0)
                + (1 if source.missing else 0)
                + (1 if source.missing_value else 0)
            ) > 1:
                raise AssertionError(
                    "No more than one of required, missing, and missing_value may be given "
                    "per source"
                )
        else:
            self.source = ZipSource(source)

        self.it = iter(self.source.source)

        try:
            self.value = next(self.it)
        except StopIteration:
            self.active = False
        else:
            self.active = True
            self.key = self.source.key(self.value) if self.source.key else self.value
            self.result = (
                self.source.value(self.value) if self.source.value else self.value
            )

    def __lt__(self, other: "_Pointer") -> bool:
        return self.key < other.key

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Pointer) and self.key == other.key

    def __str__(self) -> str:
        if not self.active:
            return "inactive"
        return f"raw {self.value} => key {self.key} value {self.result}"

    def increment(self) -> None:
        assert self.active
        oldkey = self.key
        try:
            self.value = next(self.it)
        except StopIteration:
            # print(f"Stop iteration; last key {self.key}")
            self.active = False
            return

        self.key = self.source.key(self.value) if self.source.key else self.value
        self.result = self.source.value(self.value) if self.source.value else self.value

        if self.key <= oldkey:
            name = (
                f'iterator "{self.source.name}"' if self.source.name else "an iterator"
            )
            raise IndexError(
                f"Sort error: {name} yielded {self.key} immediately after {oldkey}"
            )
