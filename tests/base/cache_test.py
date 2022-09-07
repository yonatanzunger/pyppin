import threading
import unittest
from typing import Any, Dict

from pyppin.base.cache import cache, cachemethod

shared_lock = threading.Lock()
shared_cache: Dict[str, Any] = {}


class MemoizedClass(object):
    def __init__(self) -> None:
        self.cache: Dict[str, Any] = {}
        self.calls = 0

    @cachemethod(cache="cache", key=lambda x, y: y)  # type: ignore
    def method_with_instance_cache(self, arg: str) -> str:
        self.calls += 1
        return "fn" + arg

    @cachemethod(cache=dict, key=lambda x, y: y)  # type: ignore
    def method_with_type_cache(self, arg: str) -> str:
        self.calls += 1
        return "fn" + arg

    @cachemethod(cache=shared_cache, key=lambda x, y: y)  # type: ignore
    def method_with_object_cache(self, arg: str) -> str:
        self.calls += 1
        return "fn" + arg

    @cachemethod(cache=dict)  # type: ignore
    def method_with_DefaultKey(self, arg: str) -> str:
        self.calls += 1
        return "def" + arg


function_call_count = 0


@cache
def function_with_type_cache(arg: str) -> str:
    global function_call_count
    function_call_count += 1
    return "fn" + arg


class MemoizeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.foo = MemoizedClass()
        shared_cache.clear()

        global function_call_count
        function_call_count = 0

    def testinstance_cache(self) -> None:
        self.assertEqual(0, self.foo.calls)
        self.assertFalse(self.foo.method_with_instance_cache.incache("bar"))

        self.assertEqual("fnbar", self.foo.method_with_instance_cache("bar"))
        self.assertEqual(1, self.foo.calls)
        self.assertTrue(self.foo.method_with_instance_cache.incache("bar"))

        self.assertEqual("fnbar", self.foo.method_with_instance_cache("bar"))
        self.assertEqual(1, self.foo.calls)
        self.assertTrue(self.foo.method_with_instance_cache.incache("bar"))

        # White-box test
        self.assertEqual({"bar": "fnbar"}, self.foo.cache)

    def testSkipCacheRead(self) -> None:
        self.assertEqual(0, self.foo.calls)
        self.assertEqual("fnbar", self.foo.method_with_instance_cache("bar"))
        self.assertEqual(1, self.foo.calls)
        self.assertEqual("fnbar", self.foo.method_with_instance_cache("bar", _skip="r"))
        self.assertEqual(2, self.foo.calls)

        # White-box test
        self.assertEqual({"bar": "fnbar"}, self.foo.cache)

    def testSkipCacheWrite(self) -> None:
        self.assertEqual(0, self.foo.calls)
        self.assertEqual("fnbar", self.foo.method_with_instance_cache("bar", _skip="w"))
        self.assertEqual(1, self.foo.calls)

        self.assertEqual({}, self.foo.cache)  # White-box test

        self.assertEqual("fnbar", self.foo.method_with_instance_cache("bar"))
        self.assertEqual(2, self.foo.calls)

        # White-box test
        self.assertEqual({"bar": "fnbar"}, self.foo.cache)

        self.assertEqual("fnbar", self.foo.method_with_instance_cache("bar"))
        # This time it hits the cache
        self.assertEqual(2, self.foo.calls)

    def testMethodtype_cache(self) -> None:
        self.assertEqual(0, self.foo.calls)
        self.assertFalse(self.foo.method_with_type_cache.incache("bar"))

        self.assertEqual("fnbar", self.foo.method_with_type_cache("bar"))
        self.assertEqual(1, self.foo.calls)
        self.assertTrue(self.foo.method_with_type_cache.incache("bar"))

        self.assertEqual("fnbar", self.foo.method_with_type_cache("bar"))
        self.assertEqual(1, self.foo.calls)
        self.assertTrue(self.foo.method_with_type_cache.incache("bar"))

        # We shouldn't have used this!
        self.assertEqual({}, self.foo.cache)

    def testMethodobject_cache(self) -> None:
        self.assertEqual(0, self.foo.calls)
        self.assertFalse(self.foo.method_with_object_cache.incache("bar"))

        self.assertEqual("fnbar", self.foo.method_with_object_cache("bar"))
        self.assertEqual(1, self.foo.calls)
        self.assertTrue(self.foo.method_with_object_cache.incache("bar"))

        self.assertEqual("fnbar", self.foo.method_with_object_cache("bar"))
        self.assertEqual(1, self.foo.calls)
        self.assertTrue(self.foo.method_with_object_cache.incache("bar"))

        # We shouldn't have used this!
        self.assertEqual({}, self.foo.cache)
        self.assertEqual({"bar": "fnbar"}, shared_cache)

    def testFunctiontype_cache(self) -> None:
        self.assertEqual(0, function_call_count)
        self.assertFalse(function_with_type_cache.incache("bar"))

        self.assertEqual("fnbar", function_with_type_cache("bar"))
        self.assertEqual(1, function_call_count)
        self.assertTrue(function_with_type_cache.incache("bar"))

        self.assertEqual("fnbar", function_with_type_cache("bar"))
        self.assertEqual(1, function_call_count)
        self.assertTrue(function_with_type_cache.incache("bar"))


if __name__ == "__main__":
    unittest.main()
