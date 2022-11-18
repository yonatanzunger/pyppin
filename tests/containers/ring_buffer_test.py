import unittest
from typing import Iterable, Iterator, List, Optional, Union

from pyppin.containers.ring_buffer import RingBuffer, T


class TestingRingBuffer(RingBuffer[T]):
    """This is a RingBuffer that also has a list representation so that it can track the invariant
    that setop(X) == setop(A)[-capacity:].
    """

    def __init__(self, capacity: int, value: Optional[Iterable[T]] = None) -> None:
        self.list: List[T] = []
        super().__init__(capacity, value)

    def __setitem__(
        self, index: Union[int, slice], value: Union[T, Iterable[T]]
    ) -> None:
        super().__setitem__(index, value)  # type: ignore
        self.list.__setitem__(index, value)  # type: ignore
        self.list = self.list[-self.capacity :] if self.capacity else []


class RingBufferTest(unittest.TestCase):
    def _expect(self, buf: TestingRingBuffer[str], values: List[str]) -> None:
        """Assert that buf's contents, as an array, are values."""
        self.assertEqual(len(values), len(buf))
        self.assertEqual(values, list(buf))
        self.assertLessEqual(len(buf._data), buf._capacity, f"Bad data: {buf._data}")

    def test_zero_capacity_buffer(self) -> None:
        buf = TestingRingBuffer[str](0)
        self.assertEqual(0, buf.capacity)
        self._expect(buf, [])

        buf.append("foo")
        self._expect(buf, [])

        with self.assertRaises(IndexError):
            buf[1:2] = "foo"

    def test_capacity_one(self) -> None:
        buf = TestingRingBuffer[str](1)
        self.assertEqual(1, buf.capacity)
        self._expect(buf, [])

        buf.append("foo")
        self._expect(buf, ["foo"])

        buf.append("bar")
        self._expect(buf, ["bar"])

        buf.clear()
        self._expect(buf, [])

    def test_capacity_three(self) -> None:
        buf = TestingRingBuffer[str](3)
        self.assertEqual(3, buf.capacity)
        self._expect(buf, [])

        buf.append("one")
        self._expect(buf, ["one"])

        buf.append("two")
        self._expect(buf, ["one", "two"])

        buf.append("three")
        self._expect(buf, ["one", "two", "three"])

        buf.append("four")
        self._expect(buf, ["two", "three", "four"])

        buf.append("five")
        self._expect(buf, ["three", "four", "five"])

        buf.append("six")
        self._expect(buf, ["four", "five", "six"])

        # Logically: This insert turns it into ['four', 'xxx', 'five', 'six'], and the four then
        # falls off the back.
        buf.insert(1, "xxx")
        self._expect(buf, ["xxx", "five", "six"])

    def test_slice_gets_aligned(self) -> None:
        # Set up a ring buffer with some stuff in it. We'll do our first tests on an "aligned"
        # buffer.
        buf = TestingRingBuffer[str](4, ["one", "two", "three", "four"])
        self.assertEqual(4, buf.capacity)
        self._expect(buf, ["one", "two", "three", "four"])
        self.assertEqual(
            0, buf._start
        )  # White-box check that we're looking at the right case

        self.assertEqual(["one", "two", "three", "four"], buf[:])
        self.assertEqual(["two", "three", "four"], buf[1:])
        self.assertEqual(["one", "two"], buf[:2])
        self.assertEqual(["three", "four"], buf[-2:])
        self.assertEqual(["one", "three"], buf[::2])

    def test_slice_gets_unaligned(self) -> None:
        buf = TestingRingBuffer[str](4, ["one", "two", "three", "four"])
        buf.extend(["five", "six"])
        self.assertEqual(4, buf.capacity)
        self._expect(buf, ["three", "four", "five", "six"])

        # White-box checks to make sure we know where we are
        self.assertEqual(2, buf._start)
        self.assertEqual(4, buf._size)
        self.assertEqual(["five", "six", "three", "four"], buf._data)

        # Black-box unittests
        self.assertEqual(["three", "four", "five", "six"], buf[:])
        self.assertEqual(["four", "five", "six"], buf[1:])
        self.assertEqual(["three", "four", "five"], buf[:3])
        self.assertEqual(["five", "six"], buf[-2:])
        self.assertEqual(["three", "five"], buf[::2])
        self.assertEqual(["four", "six"], buf[1::2])

    def test_slice_sets_zero_capacity(self) -> None:
        buf = TestingRingBuffer[str](0)
        self._expect(buf, [])

        with self.assertRaises(IndexError):
            buf[0] = "foo"

        with self.assertRaises(IndexError):
            buf[1:2] = ["foo"]

    def test_slice_sets(self) -> None:
        buf = TestingRingBuffer[str](3, ["alpha"])

        self._expect(buf, ["alpha"])

        # This is quasi-white-box, as I want to test each of the six cases in __setitem__
        # explicitly.

        # This is a generator rather than an array, so we explicitly *don't* know its length using
        # __len__, to test those cases.
        def source(prefix: str, max_len: Optional[int] = None) -> Iterator[str]:
            count = 0
            while max_len is None or count < max_len:
                result = f"{prefix}-{count}"
                print(f"       YIELD {result}")
                yield result
                # yield f'{prefix}-{count}'
                count += 1

        # Case 1: Integer index set.
        buf[0] = "delta"
        self._expect(buf, ["delta"])

        # Case 2: Append with a gap
        with self.assertRaises(IndexError):
            buf[2] = "echo"
        self._expect(buf, ["delta"])

        # Case 3: Append with no gap, i.e. extend.
        buf[1:] = ["foxtrot", "golf"]
        self._expect(buf, ["delta", "foxtrot", "golf"])

        # Case 4a: Equal-length sequence replacement from an array
        buf[1:3] = ["hotel", "iowa"]
        self._expect(buf, ["delta", "hotel", "iowa"])

        # Case 4b: Equal-length replacement from an iterator
        buf[0:2] = source("4b", 2)
        self._expect(buf, ["4b-0", "4b-1", "iowa"])

        # Cases 4c and 4d are commented out because this functionality has been taken out. If it's
        # ever reinstated, here are some nice tests.

        # Case 4c: Equal-length replacement with an extended slice
        # buf[0:3:2] = source('4c', 2)
        # self._expect(buf, ['4c-0', '4b-1', '4c-1'])

        # Case 4d: Not actually equal-length replacement with an extended slice
        # with self.assertRaises(ValueError):
        #     buf[0:3:2] = source('4d', 3)

        # Case 5a: Replace with something shorter of known length
        buf[0:2] = ["5a"]
        self._expect(buf, ["5a", "iowa"])

        # Case 5b: Replace with something longer of known length, but don't wrap
        buf[1:2] = ["5b-1", "5b-2"]
        self._expect(buf, ["5a", "5b-1", "5b-2"])

        # Case 5c: Replace with something longer of known length, and do wrap
        # Replacing this interval on a list would give us ['5a', '5c-1', '5c-2', '5c-3', '5b-2'].
        # Since it's a ring buffer of length 3, we should just get the last three elements of that.
        buf[1:2] = ["5c-1", "5c-2", "5c-3"]
        self._expect(buf, ["5c-2", "5c-3", "5b-2"])

        # Case 6: Replace with something longer of unknown length.
        buf[2:3] = source("6", 2)
        self._expect(buf, ["5c-3", "6-0", "6-1"])


# Tests:
# - zero capacity
# - capacity 1
# - capacity 3
# - slice gets (int, simple, extended, does and doesn't overlap edge)
# - slice sets (int, simple / same size, simple / different size, extended)
# - slice deletes (int, simple)
# - insert, append
# - iterator, reversed
