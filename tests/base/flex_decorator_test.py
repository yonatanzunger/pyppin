import unittest
from typing import Any, Callable, Tuple

from pyppin.base.flex_decorator import flex_decorator


class FlexDecoratorTest(unittest.TestCase):
    def test_with_defaults(self) -> None:
        # We'll define a silly decorator that returns (decorator_arg, return value).
        @flex_decorator
        def decorator_with_defaults(target: Callable, *, arg: int = 2) -> Callable:
            def wrapped_function(*args: Any, **kwargs: Any) -> Tuple[int, Any]:
                return (arg, target(*args, **kwargs))

            return wrapped_function

        # You can use it without arguments
        @decorator_with_defaults
        def test_function(x: str) -> str:
            return "foo_" + x

        self.assertEqual((2, "foo_bar"), test_function("bar"))

        # Or with arguments
        @decorator_with_defaults(arg=3)  # type: ignore
        def another_test_function(x: str) -> str:
            return "quux_" + x

        self.assertEqual((3, "quux_bar"), another_test_function("bar"))

    def test_without_defaults(self) -> None:
        # This one has no default value for arg.
        @flex_decorator
        def decorator_without_defaults(target: Callable, *, arg: int) -> Callable:
            def wrapped_function(*args: Any, **kwargs: Any) -> Tuple[int, Any]:
                return (arg, target(*args, **kwargs))

            return wrapped_function

        # You can't use it without arguments!
        with self.assertRaises(TypeError):

            @decorator_without_defaults
            def test_function(x: str) -> str:
                return "foo_" + x

        # But you can with arguments.
        @decorator_without_defaults(arg=3)  # type: ignore
        def another_test_function(x: str) -> str:
            return "quux_" + x

        self.assertEqual((3, "quux_bar"), another_test_function("bar"))
