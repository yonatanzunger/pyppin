from typing import (Any, Callable, Generic, Iterable, Iterator, List,
                    NamedTuple, Optional, Tuple, TypeVar, Union)

ValueType = TypeVar("ValueType")
KeyType = TypeVar("KeyType")
YieldedType = TypeVar("YieldedType")


class ZipSource(NamedTuple):
    """A ZipSource is a flexible input for a Zipper, providing an iterable plus extra options."""

    # The underlying iterator. The caller must guarantee that it is strictly sorted by key: that
    # is, if source yields a and then b, key(a) < key(b).
    source: Iterable[ValueType]

    # An optional function that pulls out the sort key given any element of the source. The default
    # is to treat the entire yielded value as the key. Sort keys must be comparable with < and ==.
    key: Optional[Callable[[ValueType], KeyType]] = None

    # An optional function that pulls out the item to be yielded in the zipper output for any given
    # value type. The default is to simply yield whatever the iterator provides.
    value: Optional[Callable[[ValueType], YieldedType]] = None

    # A name for this iterator, which will be used to give nicer error messages if given.
    name: Optional[str] = None

    # The following three fields control what happens if a key shows up in some other source, but
    # not in this one. Only one of these may be given.

    # If required is true, then the zipper should skip any keys that don't appear in this one
    # source; this source is a "required field."
    required: bool = False

    # If this function is given, and this source had no value for the given key, we will yield
    # missing(key) instead.
    missing: Optional[Callable[[KeyType], YieldedType]] = None

    # If neither required nor missing was set, then we will yield this constant value for any
    # missing values.
    missingValue: Optional[YieldedType] = None


def zipper(
    *sources: Union[ZipSource, Iterable],
) -> Iterator[Tuple]:
    """Given N iterators which each yield results in sorted order, return a single iterator which
    yields the values grouped by their keys. Keys must be comparable (< and ==) across all the
    inputs.

    Example:
        Say you have two sorted lists that you want to merge:
            l1 = [1, 2, 3, 4, 5]
            l2 = [(2, "two"), (5, "five"), (7, "seven")]

        Then

            zipper(l1, ZipSource(l2, key=lambda x: x[0]))

        will yield

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

    Fancier example:
        Let's say instead you have
            squares = [1, 4, 9, 16, 25]

        You want to get, for each  number in l2, its printed name and its square.

            zipper(
                MergeSource(l1, key=lambda x: int(sqrt(x))),
                MergeSource(l2, key=lambda x: x[0], value=lambda x: x[1], required=True),
            )

        This will yield

            (2, 4, "two")
            (5, 25, "five")
            (7, None, "seven"))

        What happened here?
            => For l1, the key is the square root of the value, and the (default) value is just
               the element of l1.
            => For l2, the key is the first element of the tuple, the yielded value is the
               second element, and because required=True, all items that don't show up in l2
               are dropped outright.
            => Because l1 *isn't* required, we get one yielded item that has no value for l1!

    Args:
        sources: Each source is an Iterable, optionally passed as a MergeSource to give it
            non-default options.

    Yields:
        Tuples with N+1 entries, where N is the number of sources.

        The first item yielded is the key; outputs of the zipper will be strictly sorted
        by key, and the zipper will yield one element for every key which appears in any source, so
        long as that key appears in *every* source marked 'required'.

        The remaining items will be the corresponding values of the N iterators for that key,
        swapping in their "missing" values if any iterator didn't yield a value.

    Raises:
        IndexError if any of the lists is *not* actually sorted in the correct way.
        AssertionError if invalid options were passed for any source.
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
    result = [None] * (len(sources) + 1)

    while True:
        # Grab the pointer that's currently farthest behind.
        key = ptrs[minkey].key
        print(f'Loop start: key is {key} from {minkey}')

        # Let's assemble the result for this key! We're going to reuse this array, since the logic
        # below guarantees that we'll either skip the whole output, or fill in every field of the
        # result.
        result[0] = key
        skip = False
        minkey = -1

        for index, ptr in enumerate(ptrs):
            print(f'{index}: {ptr}')
            if ptr.active and ptr.key == key:
                # Match! Add this to the result and increment the pointer.
                result[index + 1] = ptr.result
                ptr.increment()
                print(f'  Update {index} to {ptr}')
            elif ptr.source.required:
                # Don't worry about updating result in this case, we aren't going to output.
                skip = True
            elif ptr.source.missing:
                result[index + 1] = ptr.source.missing(key)
            else:
                result[index + 1] = ptr.source.missingValue

            # And update minkey
            if ptr.active and (minkey == -1 or ptr.key < ptrs[minkey].key):
                minkey = index

        print(f'Loop finished: skip {skip} minkey {minkey} yielded {result}')
        if not skip:
            yield tuple(result)

        if minkey == -1:
            # Nothing left! We're done.
            return


def _identity(x: Any) -> Any:
    return x


def _makeSource(source: Union[ZipSource, Iterator]) -> ZipSource:
    if not isinstance(source, ZipSource):
        source = ZipSource(source)

    # Check values and fill in defaults
    if (
        (1 if source.required else 0)
        + (1 if source.missing else 0)
        + (1 if source.missingValue else 0)
    ) > 1:
        raise AssertionError(
            "No more than one of required, missing, and missingValue may be given "
            "per source"
        )

    if not source.key or not source.value:
        source = source._replace(
            key=source.key or _identity,
            value=source.value or _identity,
        )

    return source


class _Pointer(Generic[KeyType, ValueType, YieldedType]):
    def __init__(
        self,
        source: Union[ZipSource, Iterable],
    ) -> None:
        self.source = _makeSource(source)
        self.it = iter(self.source.source)

        try:
            self.value = next(self.it)
        except StopIteration:
            self.active = False
        else:
            self.active = True
            self.key = self.source.key(self.value)  # mypy: ignore
            self.result = self.source.value(self.value)  # mypy: ignore

    def __lt__(self, other: "_Pointer") -> bool:
        return self.key < other.key

    def __eq__(self, other: "_Pointer") -> bool:
        return self.key == other.key

    def __str__(self) -> str:
        if not self.active:
            return 'inactive'
        return f'raw {self.value} => key {self.key} value {self.result}'

    def increment(self) -> None:
        assert self.active
        oldkey = self.key
        try:
            self.value = next(self.it)
        except StopIteration:
            print(f'Stop iteration; last key {self.key}')
            self.active = False
            return

        self.key = self.source.key(self.value)  # mypy: ignore
        self.result = self.source.value(self.value)  # mypy: ignore
        if self.key <= oldkey:
            name = (
                f'iterator "{self.source.name}"' if self.source.name else "an iterator"
            )
            raise IndexError(
                f"Sort error: {name} yielded {self.key} immediately after {oldkey}"
            )
