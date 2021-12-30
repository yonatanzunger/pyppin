import threading
import unittest
from typing import Any, Dict

from pyppin.cache import cache, cachemethod

sharedLock = threading.Lock()
sharedCache: Dict[str, Any] = {}


class MemoizedClass(object):
    def __init__(self) -> None:
        self.cache: Dict[str, Any] = {}
        self.calls = 0

    @cachemethod(cache="cache", key=lambda x, y: y)
    def methodWithInstanceCache(self, arg: str) -> str:
        self.calls += 1
        return "fn" + arg

    @cachemethod(cache=dict, key=lambda x, y: y)
    def methodWithTypeCache(self, arg: str) -> str:
        self.calls += 1
        return "fn" + arg

    @cachemethod(cache=sharedCache, key=lambda x, y: y)
    def methodWithObjectCache(self, arg: str) -> str:
        self.calls += 1
        return "fn" + arg

    @cachemethod(cache=dict)
    def methodWithDefaultKey(self, arg: str) -> str:
        self.calls += 1
        return "def" + arg


functionCallCount = 0


@cache()
def functionWithTypeCache(arg: str) -> str:
    global functionCallCount
    functionCallCount += 1
    return "fn" + arg


class MemoizeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.foo = MemoizedClass()
        sharedCache.clear()

        global functionCallCount
        functionCallCount = 0

    def testInstanceCache(self) -> None:
        self.assertEqual(0, self.foo.calls)
        self.assertFalse(self.foo.methodWithInstanceCache.incache("bar"))

        self.assertEqual("fnbar", self.foo.methodWithInstanceCache("bar"))
        self.assertEqual(1, self.foo.calls)
        self.assertTrue(self.foo.methodWithInstanceCache.incache("bar"))

        self.assertEqual("fnbar", self.foo.methodWithInstanceCache("bar"))
        self.assertEqual(1, self.foo.calls)
        self.assertTrue(self.foo.methodWithInstanceCache.incache("bar"))

        # White-box test
        self.assertEqual({"bar": "fnbar"}, self.foo.cache)

    def testSkipCacheRead(self) -> None:
        self.assertEqual(0, self.foo.calls)
        self.assertEqual("fnbar", self.foo.methodWithInstanceCache("bar"))
        self.assertEqual(1, self.foo.calls)
        self.assertEqual("fnbar", self.foo.methodWithInstanceCache("bar", _skip="r"))
        self.assertEqual(2, self.foo.calls)

        # White-box test
        self.assertEqual({"bar": "fnbar"}, self.foo.cache)

    def testSkipCacheWrite(self) -> None:
        self.assertEqual(0, self.foo.calls)
        self.assertEqual("fnbar", self.foo.methodWithInstanceCache("bar", _skip="w"))
        self.assertEqual(1, self.foo.calls)

        self.assertEqual({}, self.foo.cache)  # White-box test

        self.assertEqual("fnbar", self.foo.methodWithInstanceCache("bar"))
        self.assertEqual(2, self.foo.calls)

        # White-box test
        self.assertEqual({"bar": "fnbar"}, self.foo.cache)

        self.assertEqual("fnbar", self.foo.methodWithInstanceCache("bar"))
        # This time it hits the cache
        self.assertEqual(2, self.foo.calls)

    def testMethodTypeCache(self) -> None:
        self.assertEqual(0, self.foo.calls)
        self.assertFalse(self.foo.methodWithTypeCache.incache("bar"))

        self.assertEqual("fnbar", self.foo.methodWithTypeCache("bar"))
        self.assertEqual(1, self.foo.calls)
        self.assertTrue(self.foo.methodWithTypeCache.incache("bar"))

        self.assertEqual("fnbar", self.foo.methodWithTypeCache("bar"))
        self.assertEqual(1, self.foo.calls)
        self.assertTrue(self.foo.methodWithTypeCache.incache("bar"))

        # We shouldn't have used this!
        self.assertEqual({}, self.foo.cache)

    def testMethodObjectCache(self) -> None:
        self.assertEqual(0, self.foo.calls)
        self.assertFalse(self.foo.methodWithObjectCache.incache("bar"))

        self.assertEqual("fnbar", self.foo.methodWithObjectCache("bar"))
        self.assertEqual(1, self.foo.calls)
        self.assertTrue(self.foo.methodWithObjectCache.incache("bar"))

        self.assertEqual("fnbar", self.foo.methodWithObjectCache("bar"))
        self.assertEqual(1, self.foo.calls)
        self.assertTrue(self.foo.methodWithObjectCache.incache("bar"))

        # We shouldn't have used this!
        self.assertEqual({}, self.foo.cache)
        self.assertEqual({"bar": "fnbar"}, sharedCache)

    def testFunctionTypeCache(self) -> None:
        self.assertEqual(0, functionCallCount)
        self.assertFalse(functionWithTypeCache.incache("bar"))

        self.assertEqual("fnbar", functionWithTypeCache("bar"))
        self.assertEqual(1, functionCallCount)
        self.assertTrue(functionWithTypeCache.incache("bar"))

        self.assertEqual("fnbar", functionWithTypeCache("bar"))
        self.assertEqual(1, functionCallCount)
        self.assertTrue(functionWithTypeCache.incache("bar"))


if __name__ == "__main__":
    unittest.main()
