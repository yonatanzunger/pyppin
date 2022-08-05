import unittest
from typing import List

from pyppin.containers.ring_buffer import RingBuffer


class RingBufferTest(unittest.TestCase):
    def _expect(self, buf: RingBuffer[str], values: List[str]) -> None:
        """Assert that buf's contents, as an array, are values."""
        self.assertEqual(len(values), len(buf))
        self.assertEqual(values, list(buf))
        self.assertEqual(values, buf[:])

    def test_zero_capacity_buffer(self) -> None:
        buf = RingBuffer[str](0)
        self.assertEqual(0, buf.capacity)
        self._expect(buf, [])

        buf.append('foo')
        self._expect(buf, [])

        with self.assertRaises(IndexError):
            buf[1:2] = 'foo'

    def test_capacity_one(self) -> None:
        buf = RingBuffer[str](1)
        self.assertEqual(1, buf.capacity)
        self._expect(buf, [])

        buf.append('foo')
        self._expect(buf, ['foo'])

        buf.append('bar')
        self._expect(buf, ['bar'])

        buf.clear()
        self._expect(buf, [])

    def test_capacity_three(self) -> None:
        buf = RingBuffer[str](3)
        self.assertEqual(3, buf.capacity)
        self._expect(buf, [])

        buf.append('one')
        self._expect(buf, ['one'])

        buf.append('two')
        self._expect(buf, ['one', 'two'])

        buf.append('three')
        self._expect(buf, ['one', 'two', 'three'])

        buf.append('four')
        self._expect(buf, ['two', 'three', 'four'])

        buf.append('five')
        self._expect(buf, ['three', 'four', 'five'])

        buf.append('six')
        self._expect(buf, ['four', 'five', 'six'])

        # Logically: This insert turns it into ['four', 'xxx', 'five', 'six'], and the four then
        # falls off the back.
        buf.insert(1, 'xxx')
        self._expect(buf, ['xxx', 'five', 'six'])

    def test_slice_gets_aligned(self) -> None:
        # Set up a ring buffer with some stuff in it. We'll do our first tests on an "aligned"
        # buffer.
        buf = RingBuffer[str](4, ['one', 'two', 'three', 'four'])
        self.assertEqual(4, buf.capacity)
        self._expect(buf, ['one', 'two', 'three', 'four'])
        self.assertEqual(0, buf._start)  # White-box check that we're looking at the right case

        self.assertEqual(['one', 'two', 'three', 'four'], buf[:])
        self.assertEqual(['two', 'three', 'four'], buf[1:])
        self.assertEqual(['one', 'two'], buf[:2])
        self.assertEqual(['three', 'four'], buf[-2:])
        self.assertEqual(['one', 'three'], buf[::2])

    def test_slice_gets_unaligned(self) -> None:
        buf = RingBuffer[str](4, ['one', 'two', 'three', 'four'])
        buf.extend(['five', 'six'])
        self.assertEqual(4, buf.capacity)
        self._expect(buf, ['three', 'four', 'five', 'six'])

        # White-box checks to make sure we know where we are
        self.assertEqual(2, buf._start)
        self.assertEqual(4, buf._size)
        self.assertEqual(['five', 'six', 'three', 'four'], buf._data)

        # Black-box unittests
        self.assertEqual(['three', 'four', 'five', 'six'], buf[:])
        self.assertEqual(['four', 'five', 'six'], buf[1:])
        self.assertEqual(['three', 'four', 'five'], buf[:3])
        self.assertEqual(['five', 'six'], buf[-2:])
        self.assertEqual(['three', 'five'], buf[::2])
        self.assertEqual(['four', 'six'], buf[1::2])

    def test_slice_sets_zero_capacity(self) -> None:
        buf = RingBuffer[str](0)
        self._expect(buf, [])

        with self.assertRaises(IndexError):
            buf[0] = 'foo'

        with self.assertRaises(IndexError):
            buf[1:2] = ['foo']

    def test_slice_sets(self) -> None:
        buf = RingBuffer[str](3)
        self._expect(buf, [])

        buf[:] = ['foo']
        self._expect(buf, ['foo'])


# Tests:
# - zero capacity
# - capacity 1
# - capacity 3
# - slice gets (int, simple, extended, does and doesn't overlap edge)
# - slice sets (int, simple / same size, simple / different size, extended)
# - slice deletes (int, simple)
# - insert, append
# - iterator, reversed
