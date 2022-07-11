import io
import sys
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
                raise ValueError('Failed setup')

        def tearDown(self) -> None:
            if fail_teardown:
                raise ValueError('Failed teardown')

        def test_something(self) -> None:
            sys.__stderr__.write(f'In testSomething: {fail_method}\n')
            if fail_method:
                raise ValueError('Failed method')
            raise AssertionError('No')

    return SyntheticTestCase


def run_test_case(test: Type[unittest.TestCase]) -> unittest.TestResult:
    suite = unittest.TestSuite()
    suite.addTest(unittest.TestLoader().loadTestsFromTestCase(test))
    unittest.TextTestRunner().run(suite)
    """
    result = unittest.TestResult()
    suite.run(result)
    return result
    """


class TraceOnFailureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.maxDiff = None

    def testWrappedClass(self) -> None:
        buffer = io.StringIO()

        test_case = trace_on_failure(output=buffer)(make_test_case(fail_method=True))

        print(type(test_case))
        print(dir(test_case))
        print(test_case.setUp)

        run_test_case(test_case)
        self.assertEqual('', buffer.getvalue())
        self.assertFalse(True)
