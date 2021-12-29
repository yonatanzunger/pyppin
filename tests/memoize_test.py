import unittest
from typing import Any, Dict

from pyppin.memoize import cachemethod

sharedCache: Dict[str, Any] = {}


class MemoizedClass(object):
    def __init__(self) -> None:
        self.cache: Dict[str, Any] = {}
        self.calls = 0

    @cachemethod(var="cache", key=lambda x, y: y)
    def functionWithInstanceCache(self, arg: str) -> str:
        self.calls += 1
        return "fn" + arg

    @cachemethod(cls=dict, key=lambda x, y: y)
    def functionWithTypeCache(self, arg: str) -> str:
        self.calls += 1
        return "fn" + arg

    @cachemethod(cacheobj=sharedCache, key=lambda x, y: y)
    def functionWithObjectCache(self, arg: str) -> str:
        self.calls += 1
        return "fn" + arg

    @cachemethod(cls=dict)
    def functionWithDefaultKey(self, arg: str) -> str:
        self.calls += 1
        return "def" + arg


class MemoizeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.foo = MemoizedClass()
        sharedCache.clear()

    def testInstanceCache(self) -> None:
        self.assertEqual(0, self.foo.calls)
        self.assertFalse(self.foo.functionWithInstanceCache.incache("bar"))

        self.assertEqual("fnbar", self.foo.functionWithInstanceCache("bar"))
        self.assertEqual(1, self.foo.calls)
        self.assertTrue(self.foo.functionWithInstanceCache.incache("bar"))

        self.assertEqual("fnbar", self.foo.functionWithInstanceCache("bar"))
        self.assertEqual(1, self.foo.calls)
        self.assertTrue(self.foo.functionWithInstanceCache.incache("bar"))

        # White-box test
        self.assertEqual({"bar": "fnbar"}, self.foo.cache)

    def testSkipCacheRead(self) -> None:
        self.assertEqual(0, self.foo.calls)
        self.assertEqual("fnbar", self.foo.functionWithInstanceCache("bar"))
        self.assertEqual(1, self.foo.calls)
        self.assertEqual("fnbar", self.foo.functionWithInstanceCache("bar", _skip="r"))
        self.assertEqual(2, self.foo.calls)

        # White-box test
        self.assertEqual({"bar": "fnbar"}, self.foo.cache)

    def testSkipCacheWrite(self) -> None:
        self.assertEqual(0, self.foo.calls)
        self.assertEqual("fnbar", self.foo.functionWithInstanceCache("bar", _skip="w"))
        self.assertEqual(1, self.foo.calls)

        self.assertEqual({}, self.foo.cache)  # White-box test

        self.assertEqual("fnbar", self.foo.functionWithInstanceCache("bar"))
        self.assertEqual(2, self.foo.calls)

        # White-box test
        self.assertEqual({"bar": "fnbar"}, self.foo.cache)

        self.assertEqual("fnbar", self.foo.functionWithInstanceCache("bar"))
        # This time it hits the cache
        self.assertEqual(2, self.foo.calls)

    def testTypeCache(self) -> None:
        self.assertEqual(0, self.foo.calls)
        self.assertFalse(self.foo.functionWithTypeCache.incache("bar"))

        self.assertEqual("fnbar", self.foo.functionWithTypeCache("bar"))
        self.assertEqual(1, self.foo.calls)
        self.assertTrue(self.foo.functionWithTypeCache.incache("bar"))

        self.assertEqual("fnbar", self.foo.functionWithTypeCache("bar"))
        self.assertEqual(1, self.foo.calls)
        self.assertTrue(self.foo.functionWithTypeCache.incache("bar"))

        # We shouldn't have used this!
        self.assertEqual({}, self.foo.cache)

    def testObjectCache(self) -> None:
        self.assertEqual(0, self.foo.calls)
        self.assertFalse(self.foo.functionWithObjectCache.incache("bar"))

        self.assertEqual("fnbar", self.foo.functionWithObjectCache("bar"))
        self.assertEqual(1, self.foo.calls)
        self.assertTrue(self.foo.functionWithObjectCache.incache("bar"))

        self.assertEqual("fnbar", self.foo.functionWithObjectCache("bar"))
        self.assertEqual(1, self.foo.calls)
        self.assertTrue(self.foo.functionWithObjectCache.incache("bar"))

        # We shouldn't have used this!
        self.assertEqual({}, self.foo.cache)
        self.assertEqual({"bar": "fnbar"}, sharedCache)


if __name__ == "__main__":
    unittest.main()
