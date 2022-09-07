import io
import unittest
from typing import Type

from pyppin.testing.trace_on_failure import trace_on_failure


def make_test_case(
    fail_setup: bool = False,
    fail_teardown: bool = False,
    fail_method: bool = False,
) -> Type[unittest.TestCase]:
    class SyntheticTestCase(unittest.TestCase):
        def setUp(self) -> None:
            if fail_setup:
                raise ValueError("Failed setup")

        def tearDown(self) -> None:
            if fail_teardown:
                raise ValueError("Failed teardown")

        def test_something(self) -> None:
            if fail_method:
                raise ValueError("Failed method")
            self.fail("Ordinary test case failure")

    return SyntheticTestCase


def run_test_case(
    test: Type[unittest.TestCase], debug_show_test_result: bool = False
) -> None:
    # You can set debug_show_test_result to True if you want to see the output of all the unittests
    # on stderr, which is useful when you're debugging the test itself.
    suite = unittest.TestSuite()
    suite.addTest(unittest.TestLoader().loadTestsFromTestCase(test))
    buffer = None if debug_show_test_result else io.StringIO()
    unittest.TextTestRunner(stream=buffer).run(suite)


class TraceOnFailureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.maxDiff = None

    def testWrappedClassTestRaisesException(self) -> None:
        buffer = io.StringIO()

        test_case = trace_on_failure(output=buffer)(make_test_case(fail_method=True))

        run_test_case(test_case)
        result = buffer.getvalue()
        self.assertIn('Thread "MainThread"', result)
        self.assertIn("ValueError: Failed method", result)

    def testWrappedClassTestFails(self) -> None:
        # When a unittest fails, rather than raises an exception, it shouldn't dump a stack trace.
        buffer = io.StringIO()

        test_case = trace_on_failure(output=buffer)(make_test_case())

        run_test_case(test_case)
        self.assertEqual("", buffer.getvalue())

    def testWrappedClassFailSetUp(self) -> None:
        # Test that the wrapper captures failures in test harness methods
        buffer = io.StringIO()

        test_case = trace_on_failure(output=buffer)(
            make_test_case(fail_setup=True, fail_method=True)
        )

        run_test_case(test_case)
        result = buffer.getvalue()
        self.assertIn('Thread "MainThread"', result)
        self.assertIn("ValueError: Failed setup", result)
        self.assertNotIn("ValueError: Failed method", result)

    def testWrappedFunction(self) -> None:
        buffer = io.StringIO()

        @trace_on_failure(output=buffer)  # type: ignore
        def failing_function() -> None:
            raise ValueError("Failed function")

        with self.assertRaises(ValueError):
            failing_function()

        result = buffer.getvalue()
        self.assertIn('Thread "MainThread"', result)
        self.assertIn("ValueError: Failed function", result)
