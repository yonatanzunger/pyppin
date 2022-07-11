import functools
import io
import itertools
import unittest
from typing import Callable, Optional, Type, Union

from pyppin.threading.stack_trace import print_all_stacks


def trace_on_failure(
    output: Optional[io.TextIOBase] = None,
    limit: Optional[int] = None,
    daemons: bool = True,
    group: bool = True,
    exclude_assertion_failures: bool = True,
):
    """Decorator which can be applied to functions, methods, and TestCases. If any exception happens
    while executing the item, dump a full stack trace (of all active threads) to output.

    Args:
        output: Where to write the output; defaults to stderr.
        limit: As the argument to all_stacks.
        daemons: Whether to include daemon threads.
        group: If True, group together threads with identical traces.
        exclude_assertion_failures: If this decorator is applied to a TestCase, then it will
            only print stack traces on exceptions, not on assertion failures from within the test.
    """

    def _decorate(target: Union[Callable, Type[unittest.TestCase]]):
        if isinstance(target, type) and issubclass(target, unittest.TestCase):
            return _decorate_test_case(
                target,
                output=output,
                limit=limit,
                daemons=daemons,
                group=group,
                exclude_assertion_failures=exclude_assertion_failures,
            )
        else:
            return _decorate_function(
                target, output=output, daemons=daemons, group=group, limit=limit
            )

    return _decorate


def _decorate_function(
    fn: Callable,
    output: Optional[io.TextIOBase],
    limit: Optional[int],
    daemons: bool,
    group: bool,
    exclude: Optional[Type[Exception]] = None,
) -> Callable:
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except BaseException as e:
            if exclude is None or not issubclass(type(e), exclude):
                print_all_stacks(output=output, limit=limit, daemons=daemons, group=group)
            raise

    return wrapped


_TEST_METHODS = {'setUp', 'tearDown', 'setUpClass', 'tearDownClass'}


def _decorate_test_case(
    test: Type[unittest.TestCase],
    output: Optional[io.TextIOBase],
    limit: Optional[int],
    daemons: bool,
    group: bool,
    exclude_assertion_failures: bool,
) -> unittest.TestCase:
    exclude = test.failureException if exclude_assertion_failures else None

    for name in itertools.chain(_TEST_METHODS, unittest.TestLoader().getTestCaseNames(test)):
        if hasattr(test, name):
            setattr(
                test,
                name,
                _decorate_function(
                    getattr(test, name),
                    exclude=exclude,
                    output=output,
                    limit=limit,
                    daemons=daemons,
                    group=group,
                ),
            )

    return test
