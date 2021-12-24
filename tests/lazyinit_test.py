import unittest

from pyppin.lazyinit import lazyinit, resetAll


class LazyInitStruct(object):
    def __init__(self) -> None:
        self.calls = 0

    @lazyinit
    def value(self) -> int:
        self.calls += 1
        return 3

    @property
    def nonLazyValue(self) -> int:
        self.calls += 1
        return 4

    @lazyinit
    def anotherLazyValue(self) -> int:
        self.calls += 1
        return 5


class LazyInitTest(unittest.TestCase):
    def testNonLazyInit(self) -> None:
        foo = LazyInitStruct()
        self.assertEqual(0, foo.calls)

        self.assertEqual(4, foo.nonLazyValue)
        self.assertEqual(1, foo.calls)

        self.assertEqual(4, foo.nonLazyValue)
        self.assertEqual(2, foo.calls)

    def testLazyInit(self) -> None:
        foo = LazyInitStruct()
        self.assertEqual(0, foo.calls)

        self.assertEqual(3, foo.value)
        self.assertEqual(1, foo.calls)

        self.assertEqual(3, foo.value)
        self.assertEqual(1, foo.calls)

    def testExplicitSet(self) -> None:
        foo = LazyInitStruct()
        foo.value = 17

        self.assertEqual(0, foo.calls)
        self.assertEqual(17, foo.value)
        self.assertEqual(0, foo.calls)

    def testResetOne(self) -> None:
        foo = LazyInitStruct()
        self.assertEqual(0, foo.calls)

        self.assertEqual(3, foo.value)
        self.assertEqual(1, foo.calls)

        del foo.value

        self.assertEqual(3, foo.value)
        self.assertEqual(2, foo.calls)

    def testResetAll(self) -> None:
        foo = LazyInitStruct()
        self.assertEqual(3, foo.value)
        self.assertEqual(4, foo.nonLazyValue)
        self.assertEqual(5, foo.anotherLazyValue)
        self.assertEqual(3, foo.calls)

        self.assertEqual(3, foo.value)
        self.assertEqual(4, foo.nonLazyValue)
        self.assertEqual(5, foo.anotherLazyValue)

        resetAll(foo)

        self.assertEqual(3, foo.value)
        self.assertEqual(4, foo.nonLazyValue)
        self.assertEqual(5, foo.anotherLazyValue)
        self.assertEqual(7, foo.calls)  # All three call


if __name__ == "__main__":
    unittest.main()
