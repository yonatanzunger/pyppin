"""Call a function in a retry loop with exponential backoff."""

import random
import time
from typing import Callable, List, Optional, Type, TypeVar, Union
from urllib.error import HTTPError

ReturnType = TypeVar("ReturnType")

# TODO: The calling syntax of this function is very unsatisfactory. I find myself forgetting the key
# lambdas, and I wrote this thing! What I would really like is to be able to say
#
# with ExponentialBackoff(...):
#   ... code block ...
#
# The problem is that with is an exception-handling construct, not a looping one. Conversely, you
# can't use a while statement there, because those can't catch exceptions. You could *almost* pull
# this off with goto statements, but they changed how those behave so that they can only be invoked
# from trace functions. There isn't any really good way to pass a code block as an argument to
# something right now, which makes me sad. Wouldn't that be a nicer syntax?


def retry(
    function: Callable[[], ReturnType],
    retry: Union[List[Type[Exception]], Callable[[Exception], bool]],
    max_attempts: Optional[int] = None,
    initial_delay: float = 0.1,
    multiplier: float = 2,
    max_delay: float = 2,
    jitter: float = 0,
    _sleep: Callable[[float], None] = time.sleep,
) -> ReturnType:
    """Call a function in a retry loop with exponential backoff.

    Some operations like RPC's can finish in three ways: successfully, with a non-retriable error
    (like an HTTP 4xx), or with a retriable error (like an HTTP 5xx). In the latter case, you want
    to try again, but you *don't* want to simply call the function in a loop. That's because a
    common cause of 5xx's and the like is that the target system is overloaded; if clients responded
    to an overload by asking again immediately, that would make the overload *worse*, leading to a
    "thundering herd" problem.

    The solution is to call in a loop, but wait a bit between successive retries. The recommended
    algorithm is an exponential backoff: first wait X time, then 2X time, then 4X, and so on,
    backing off more and more up to some maximum.

    This class handles all of that logic. If your original call was::

        result = do_something_retriable(arg1, arg2)

    then now you call::

        result = retry(
            lambda: do_something_retriable(arg1, arg2),
            retry=[TimeoutError],
        )

    The first argument is a zero-argument function that does the thing you want to retry. If your
    thing to retry is just a function call, then sticking a "lambda:" before it should do the trick.
    (Since that creates a function with no arguments that does the thing you describe) Note that you
    *CANNOT* just do_something_retriable(arg1, arg2) there, because that would just evaluate the
    thing right there and pass its *result* to retry(), which wouldn't work!

    The second argument says which kinds of errors should be retried; it can either be a list of
    Exception types, or a function that takes an Exception and returns a bool for "yes, retry
    this." If you're retrying HTTP requests, you might want to use the 'http_500s' function in this
    file for that.

    Other arguments control how retrying works in more detail.

    Args:
        function: A zero-argument function that does the thing you want to call.
        retry: A filter for which errors you want to retry. This can either be a list of Exception
            types ("retry anything in this category") or a function that takes an exception and
            returns a bool ("retry anything for which this is true"). For standard HTTP requests,
            you may want to use the http_retries function in this library.
        max_attempts: If not None, the maximum number of times to try. If you exceed the max retry
            count, the last exception will simply be raised as usual.
        initial_delay: The length of time to wait, in seconds, before the first retry attempt.
        multiplier: The multiplicative factor by which delay times should grow from try to try.
        max_delay: The longest delay we should ever wait for.
        jitter: If nonzero, add a random value +-jitter to the amount actually waited. This is
            important if many workers might be trying to access the same service more or less in
            sync; if you have 1,000 workers, each of which is backing off in perfect sync, then
            they'll all do their retries at once, which is *also* pretty much sure to fail. In that
            case, sticking in maybe 0.05sec of jitter should make the problem go away.
    """
    backoff = _BackoffCounter(
        retry,
        max_attempts=max_attempts,
        initial_delay=initial_delay,
        multiplier=multiplier,
        max_delay=max_delay,
        jitter=jitter,
        _sleep=_sleep,
    )
    while True:
        try:
            return function()
        except Exception as e:
            if not backoff.should_retry(e):
                raise


def http_500s(e: Exception) -> bool:
    """Helper function: Pass this to retry() to retry HTTP 500's."""
    return isinstance(e, HTTPError) and e.code >= 500


class _BackoffCounter(object):
    def __init__(
        self,
        retry: Union[List[Type[Exception]], Callable[[Exception], bool]],
        max_attempts: Optional[int] = None,
        initial_delay: float = 0.1,
        multiplier: float = 2,
        max_delay: float = 2,
        jitter: float = 0,
        _sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.retry = (
            (lambda x: any(isinstance(x, t) for t in retry))
            if isinstance(retry, list)
            else retry
        )
        self.attempt = 0
        self.max_attempts = max_attempts
        self.delay = initial_delay
        self.multiplier = multiplier
        self.max_delay = max_delay
        self.jitter = jitter
        self.sleep = _sleep

    def should_retry(self, e: Exception) -> bool:
        """If we should retry, wait and return true; otherwise, return false immediately."""
        if self.max_attempts is not None and self.attempt >= self.max_attempts:
            return False
        if not self.retry(e):
            return False
        jitter = self.jitter * (2 * random.random() - 1) if self.jitter > 0 else 0
        self.sleep(self.delay + jitter)
        self.delay = min(self.delay * self.multiplier, self.max_delay)
        self.attempt += 1
        return True
