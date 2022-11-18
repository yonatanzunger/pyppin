from collections.abc import MutableSequence
from itertools import islice
from typing import Iterable, Iterator, List, Optional, Tuple, TypeVar, Union, overload

T = TypeVar("T")


class RingBuffer(MutableSequence[T]):
    """A RingBuffer is a ring, or circular, array of fixed size.

    It's easiest to imagine as a literally circular array with [capacity] slots in it. If you
    append a further item, it starts to overwrite all items. Thus its size is always <= its
    capacity.

    This is a very useful data structure for when you want to keep the last N results that
    you've seen, or similar windowing operations.

    If you need to reason about complicated slice sets or the like with a ring buffer, remember
    this simple mnemonic: if X is a ring buffer and A is an ordinary list, which start out with
    the same contents, then

        setoperation(X) = setoperation(A)[-X.capacity:]

    i.e., it should always give you the same thing that you would get from a list, just
    truncated to the most recent <capacity> elements.

    RingBuffer does not support setting of extended slices, because this is a rarely-used
    functionality that's a lot of work to get right.

    Args:
        capacity: The size of the ring buffer.
        value: (Optional) initial values with which to populate the buffer.
    """

    def __init__(self, capacity: int, value: Optional[Iterable[T]] = None) -> None:
        # Internally: We store everything in _data, which is an array of size <= _capacity. Our
        # actual data lives at _data[_start]... _data[_start + _size % _capacity]. We'll use "index"
        # to refer to an index in the range [0, _size), i.e. the sort of index we expose in our API,
        # and "position" to refer to the corresponding position within _data.
        self._capacity = capacity
        self._start = 0
        self._size = 0
        self._data: List[T] = []
        if value is not None:
            self[:] = value

    # NB: 90% of the messiness below is dealing with slices in gets and sets, so that we can
    # actually satisfy the MutableSequence API and behave like a list. Brace yourself.

    @property
    def capacity(self) -> int:
        return self._capacity

    def __len__(self) -> int:
        return self._size

    def __contains__(self, item: object) -> bool:
        return any(item == value for value in self)

    def __iter__(self) -> Iterator[T]:
        for i in range(self._size):
            yield self._at(i)

    def __reversed__(self) -> Iterator[T]:
        for i in range(-1, -self._size - 1, -1):
            yield self._at(i)

    @overload
    def __getitem__(self, index: int) -> T:
        ...

    @overload
    def __getitem__(self, index: slice) -> List[T]:
        ...

    def __getitem__(self, index: Union[int, slice]) -> Union[T, List[T]]:
        if isinstance(index, int):
            return self._at(index)

        index = self._normalize_slice(index)
        if index.step != 1:
            # Funky case, use the slower but simpler islice.
            return list(islice(self, index.start, index.stop, index.step))

        pos_slices = self._map_slice(index)
        result = self._data[pos_slices[0]]
        for extra in pos_slices[1:]:
            result.extend(self._data[extra])
        return result

    @overload
    def __setitem__(self, index: int, value: T) -> None:
        ...

    @overload
    def __setitem__(self, index: slice, value: Iterable[T]) -> None:
        ...

    def __setitem__(
        self, index: Union[int, slice], value: Union[T, Iterable[T]]
    ) -> None:
        # CASE 1: index is an integer. By far the simplest case.
        if isinstance(index, int):
            self._set_at(index, value)  # type: ignore
            return

        # The messy case: self[slice] = [values]
        assert isinstance(index, slice)
        assert hasattr(value, "__iter__")

        # We'll start with some cases that we check *before* normalizing index, because a 'None'
        # stop value might mean something different here.

        # CASE 2: index is a slice starting *beyond* self._size, which is simply an error.
        start = index.start or 0
        if start > self._size:
            raise IndexError(f"Index {start} out of bounds")

        # CASE 3: index is a slice starting at self._size. This is equivalent to extend().
        if index.start == self._size:
            # This count is what we would get for old_data_length (below) if index.stop is not None,
            # but if it is None, this is None, signifying that we should simply drain all of value.
            count = (
                self._slice_length(index.stop, start, index.step or 1)
                if index.stop is not None
                else None
            )
            self.extend(self._limit(value, count))
            return

        # If we get here, we're replacing a slice of the original array with a new slice.
        index = self._normalize_slice(index)
        old_data_length = self._slice_length(index.start, index.stop, index.step)

        # We may or may not know the length of the new value. Since we don't need it ahead of time
        # in all cases, we'll defer trying to get it.
        new_data_length = len(value) if hasattr(value, "__len__") else None  # type: ignore

        # If we're dealing with an "extended slice" (step != 1, why does Python have these things?)
        # we need to make sure that the new length is equal to the old length, or the instruction is
        # unclear. If we don't have new_data_length, we'll have to get it the (slow, expensive) way.
        if index.step != 1:
            # This is really complicated and not really worth it.
            raise NotImplementedError(
                "Extended slice setting is not supported by RingBuffer"
            )
            if new_data_length is None:
                value = list(value)
                new_data_length = len(value)

            if old_data_length != new_data_length:
                raise ValueError(
                    f"attempt to assign sequence of length {old_data_length} to extended slice "
                    f"of size {new_data_length}"
                )

        # CASE 4: We're doing replacement of equal-length sequences, so we can just overwrite in
        # place.
        if old_data_length == new_data_length:
            for my_index, new in zip(range(index.start, index.stop, index.step), value):
                self._set_at(my_index, new)
            return

        # If we get here, we're in the messy case of replacing (contiguous, because we've ruled out
        # extended slices) chunks of non-identical size. In this case, the behavior of list, which
        # we want to duplicate, is to treat it like the old slice was chopped out and the new one
        # was put in.

        # CASE 5: If this is a sized container, we can use our _restructure method to do the
        # splicing efficiently.
        if new_data_length is not None:
            self._restructure(index.start, list(value), self._size - index.stop)
            return

        # CASE 6: In any other case, we have to do a one-by-one append.
        tail = self[index.stop :]
        self._restructure(index.start, [], 0)
        self.extend(value)
        self.extend(tail)

    def __delitem__(self, index: Union[int, slice]) -> None:
        # CASE 1: The index is an int. Delete a single item.
        if isinstance(index, int):
            self._restructure(index - 1, [], self._size - index)
            return

        # CASE 2: It's a slice.
        index = self._normalize_slice(index)
        if index.step != 1:
            raise ValueError("Deletion of extended slices is not permitted")
        self._restructure(index.start, [], self._size - index.stop)

    def insert(self, index: int, value: T) -> None:
        """The insert() operation should insert (value) at position (index), pushing higher-indexed
        items to the right. Because this is a ring buffer, this means that the lowest-indexed item
        may well fall off.
        """
        # So we turn ourselves into [:index+1] [value] [-index-1:]
        self._restructure(index, [value], self._size - index)

    def clear(self) -> None:
        self._data = []
        self._start = 0
        self._size = 0

    def append(self, value: T) -> None:
        if self._capacity == 0:
            # CASE 1: Zero-capacity buffer; do nothing.
            return
        elif self._size == self._capacity:
            # CASE 2: Buffer is full. Overwrite the element at index 0, and shift self._start, so
            # that the thing previously at index zero is now at the end.
            self._data[self._start] = value
            self._start = (self._start + 1) % self._capacity
        else:
            self._size += 1
            self._set_at(self._size - 1, value)

    def extend(self, values: Iterable[T]) -> None:
        for value in values:
            self.append(value)

    #############################################################################################
    # Internals

    def _safemod(self, value: int, by: int) -> int:
        return value % by if by > 0 else 0

    def _make_nonnegative(self, index: int) -> int:
        """Convert negative indices to positive ones if possible."""
        return index % self._size if index < 0 and self._size != 0 else index

    def _position(self, index: int, stop: bool = False) -> Tuple[int, bool]:
        """Convert an index to a position.

        Returns the position and whether or not we had to wrap around while computing it.

        If stop is True, we treat this as an (open) upper bound of a position, rather than as a true
        position.

        To understand desired behavior here, consider the case where _data = [D B C], _start = 1,
        and _size = 3. Then we would want to map index slices to position slices as:
            [0:0] -> [1:1] == empty
            [0:1] -> [1:2] == B
            [0:2] -> [1:3] == B C
            [0:3] -> [1:1] ~ [1:3] + [0:1] == B C D

        This means that start indices map to (index + _start) % _size, while stop indices map to
        (index + _start) if the result <= _size, and (index + _start) % _size otherwise.
        """
        # Make this an "unmodulated" position, which might overflow self._size
        pos = index + self._start

        # The overflow rules for start and stop indices are different; stops don't wrap until they
        # hit size + 1.
        if pos < self._size or (stop and pos == self._size):
            return (pos, False)
        else:
            return (self._safemod(pos, self._size), True)

    def _map_slice(self, index: slice) -> Tuple[slice, ...]:
        """Map a normalized index slice to one or more position slices."""
        # Special case: if start is stop, just grab nul; this avoids a weird corner case with calls
        # to _position.
        if index.start >= index.stop:
            return (slice(0, 0, 1),)

        # Now, turn them into positions. Note how start and stop positions map differently!
        start_pos, start_wrapped = self._position(index.start)
        stop_pos, stop_wrapped = self._position(index.stop, stop=True)

        if stop_wrapped and not start_wrapped:
            # We need two disjoint slices!
            return (
                slice(start_pos, self._size, index.step),
                slice(0, stop_pos, index.step),
            )
        else:
            return (slice(start_pos, stop_pos, index.step),)

    def _at(self, index: int) -> T:
        return self._data[self._position(index)[0]]

    def _normalize_slice(self, index: slice) -> slice:
        """Normalize a slice over indices to one whose elements are nonnegative, non-None, integers."""
        start = self._make_nonnegative(index.start if index.start is not None else 0)
        stop = self._make_nonnegative(
            index.stop if index.stop is not None else self._size
        )
        step = index.step or 1
        result = slice(start, stop, step)
        return result

    def _slice_length(self, start: int, stop: int, step: int) -> int:
        """Return the number of elements in a slice."""
        return max(0, ((stop - start + step - 1) // step))

    def _set_at(self, index: int, value: T) -> None:
        if index >= self._size or index <= -self._size:
            raise IndexError(f"Set index {index} out of range")
        pos = self._position(index)[0]
        if pos == len(self._data):
            self._data.append(value)
        else:
            self._data[pos] = value

    def _restructure(self, keep_head: int, data: List[T], keep_tail: int) -> None:
        """Turn self into self[:keep_head] + data + self[-keep_tail:]"""
        assert keep_head >= 0
        assert keep_tail >= 0
        assert keep_tail + keep_head <= self._size

        # Prune down to what we'll actually keep. We know keep_tail < self._capacity because of the
        # last assert (and the fact that self._size <= self._capacity) so we never need to reduce
        # that.
        if len(data) + keep_tail >= self._capacity:
            # In this case, "appending" all the items in sequence would lose all of the head, and
            # also the first (self._capacity - len(data) - keep_tail) elements of data.
            keep_head = 0
            num_to_drop = len(data) + keep_tail - self._capacity
            data = data[num_to_drop:]
        elif keep_head + len(data) + keep_tail >= self._capacity:
            keep_head = self._capacity - len(data) - keep_tail

        # We're going to want to look at the ranges self[:keep_head] and self[-keep_tail:]. But
        # there's one small problem: If keep_tail is zero, that means we want self[-0:], i.e.
        # self[self._size:], as is the convention for negative numbers in slices. But Python will
        # turn -0 into 0, so that would instead get parsed as self[0:] which is very different! So
        # we compute the position of the start of the "tail" explicitly and use that instead.
        tail_stop = self._size - keep_tail

        new_size = keep_head + keep_tail + len(data)
        assert new_size <= self._capacity
        self._data = self[:keep_head] + data + self[tail_stop:]
        self._size = new_size
        self._start = 0

    @classmethod
    def _limit(cls, it: Iterable[T], limit: Optional[int]) -> Iterator[T]:
        if limit is None:
            yield from it
        else:
            for count, value in enumerate(it):
                if count == limit:
                    break
                yield value
