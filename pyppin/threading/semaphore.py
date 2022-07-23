"""A smarter semaphore that can do things like wait for tasks to finish.

A semaphore is a shared reservior of (integer) capacity.

This is a more sophisticated version of `threading.Semaphore
<https://docs.python.org/3/library/threading.html#semaphore-objects>`_ and
`threading.BoundedSemaphore
<https://docs.python.org/3/library/threading.html#threading.BoundedSemaphore>`_: unlike
those classes, this class has a ``stop()`` method, which (irreversibly) prevents further
resource acquisition and blocks until all resources have been released. This lets you do
things like wait until all tasks have completed! It also generalizes a `threading.Barrier
<https://docs.python.org/3/library/threading.html#threading.Barrier>`_, since unlike a barrier, you
don't have to know ahead of time how many tasks need to be waited for.

Basic Usage
===========

Think of a semaphore as a reservoir of "resource," with some total amount of resource
(optionally infinity) available. You ``acquire()`` some resource at the start of an
operation, blocking until that much of the resource is available; when you're done, you
``release()`` it. This guarantees that you never use more than the available capacity at
once, which makes this an effective throttling tool. You can also change the total available
capacity with ``set_capacity()``, and shut down the entire semaphore with ``stop()``.

Because releasing what you've acquired is so important, Semaphore provides two context
manager API's::

    with semaphore:
        ... do something ...

    with semaphore.get(amount=N, timeout=X, check=bool) as resource:
        if resource:
            ... do something ...
        else:
            ... you couldn't get the capacity! ...

The first syntax grabs one unit of resource, blocking indefinitely, and raises an exception
(BrokenPipeError) if the semaphore somehow got shut down before you could get any. The
second one is a more flexible syntax that lets you control all of these behaviors; with this
syntax, you need to check whether the resource was successfully acquired.

This class is thread-safe.

Useful Ways to Use It
=====================
One common use is to **limit concurrent use of a resource**, such as an RPC server. In this
case, you can create a semaphore with some finite capacity, and have each use grab some
capacity; for example, the program might set ``throttle = Semaphore(5)`` and then have
each worker thread call::

    with throttle:
        ... do the expensive operation ...

Another common use is as a way to **make sure all tasks have finished** in a situation where you
don't know how many tasks will happen ahead of time -- for example, an RPC server might
want to enter a "lame-duck" mode where it stops accepting new requests and waits for pending
ones to finish before shutdown, or a batch job might issue a lot of asynchronous requests
and want to wait for them to finish (and yield their respective outputs) before ending
the job. A semaphore with no concurrency limit (``capacity = None``) does the trick nicely:
simply have every task ``acquire()`` when it starts and ``release()`` when it finishes, and
when you want to end the job as a whole (stop allowing new requests and wait for existing
ones to finish), the thread that wants to wait for things to finish simply calls
``Semaphore.stop()``.

Warning
=======
If a code unit (e.g. a thread, or a worker object that can move between threads) acquires some
units of resource, it **must not** acquire again until it has first released what it
holds. Otherwise you will get a thread-starvation deadlock,¹ which is notoriously hard to
catch via static analysis or unittests, and only manifests in production under high load,
when your program suddenly comes to a halt. If a code flow might need more capacity later,
acquire the maximum amount of capacity you might need up front.

¹ The exact mechanism: Say a worker holds one unit of capacity, and wants to grab one more
unit of capacity, do something, then release both. Now imagine that many identical workers
are active at once, so that the semaphore is at capacity. Every one of the workers could
release some capacity, allowing things to continue, if it could *just* get one unit of
capacity -- but there is none, and nobody can release any! The program deadlocks. This is
especially insidious because the most common reason someone might accidentally do this is if
workers only *sometimes* need that second unit of capacity. In that case, normally things
work fine: even if one worker needs an extra unit, some other worker will soon finish its
task (without needing that) and release capacity. Things only go wrong once there are enough
workers simultaneously in that special state, which tends to happen in unpredictable
circumstances but generally at peak traffic, in the middle of the night, or during a
highly-visible public event. Don't let this happen to you. Release before you acquire.
"""


from contextlib import AbstractContextManager
from enum import Enum
from threading import Condition, Lock
from time import monotonic
from types import TracebackType
from typing import NamedTuple, Optional, Type


class Semaphore(object):
    def __init__(self, capacity: Optional[int] = None) -> None:
        """Create a semaphore.

        Args:
            capacity: The maximum value of concurrent capacity which can be used, or None for an
              infinite value.
        """
        self._lock = Lock()
        self._cond = Condition(self._lock)
        self._capacity = capacity
        self._current: int = 0
        self._stopped = False

    class AcquireResult(Enum):
        """The result of an acquire() operation on a semaphore."""

        SUCCESS = 0
        """The operation succeeded; you own the resource and must release it."""

        TIMEOUT = 1
        """The operation failed because of a timeout; you don't have it, but can try again."""

        STOPPED = 2
        """The operation failed because the semaphore has been shut down.

        This is a non-retriable error; future calls will always fail.
        """

    def acquire(
        self, amount: int = 1, timeout: Optional[float] = None
    ) -> AcquireResult:
        """Acquire (take ownership of) some capacity within the semaphore.

        If this function returns SUCCESS, the capacity was successfully acquired; the caller now
        owns `amount` of resource and **must** release it, by calling ``release()``, when they are
        done using it. If the function returns any other value, the capacity was not acquired, and
        the caller owns nothing and should release nothing.

        It is guaranteed that if the timeout is zero or negative, this function will not block.

        Args:
            amount: The amount of capacity to acquire. Must be >= 0.
            timeout: How long we should block, in seconds. None (the default) means to wait
                forever. Zero means that we should never block; if we can't instantly get
                the capacity, return immediately.

        Returns:
            SUCCESS if the capacity was successfully acquired.
            TIMEOUT if the acquisition failed because time ran out.
            STOPPED if the acquisition failed because the semaphore has stopped. (This is a
            non-transient error!)
        """
        assert amount >= 0

        # We may have to wait many times, so store the total deadline time. NB that all Python
        # threading code uses time.monotonic as its underlying clock, for hopefully obvious reasons.
        deadline = monotonic() + timeout if timeout is not None else None

        with self._lock:
            while True:
                if self._stopped:
                    return self.AcquireResult.STOPPED

                if self._capacity is None or self._current + amount <= self._capacity:
                    self._current += amount
                    return self.AcquireResult.SUCCESS

                if deadline is not None:
                    now = monotonic()
                    if now >= deadline:
                        return self.AcquireResult.TIMEOUT

                    self._cond.wait(timeout=deadline - now)
                else:
                    self._cond.wait()

    def acquire_checked(self, amount: int = 1, timeout: Optional[float] = None) -> None:
        """Acquire, raising an exception on failure.

        Args:
            amount: The amount of capacity to get.
            timeout: How long we should block, in seconds. None (the default) means to wait
                forever. Zero means that we should never block; if we can't instantly get
                the capacity, return immediately.

        Raises:
            TimeoutError: If check=True, timeout != None, and the request timed out. This is a
                retriable error.
            BrokenPipeError: If check=True and the semaphore was stopped before the acquisition
                could complete. This is a non-retriable error.
        """
        result = self.acquire(amount=amount, timeout=timeout)
        if result == self.AcquireResult.TIMEOUT:
            raise TimeoutError()
        elif result == self.AcquireResult.STOPPED:
            raise BrokenPipeError()

    def try_acquire(self, amount: int = 1) -> bool:
        """Try to acquire without blocking.

        Args:
            amount: The amount of capacity to acquire.

        Returns:
            True if the capacity was acquired, false otherwise.
        """
        return self.acquire(amount=amount, timeout=0) == self.AcquireResult.SUCCESS

    def release(self, amount: int = 1) -> None:
        """Release capacity acquired via ``acquire()``."""
        if amount == 0:
            return
        assert amount > 0

        with self._lock:
            assert self._current >= amount
            self._current -= amount
            if amount == 1:
                self._cond.notify()
            else:
                # If we released multiple units, it's possible that multiple waiters need to awaken.
                # This is a less common case, and notifying everyone is very expensive, so we only
                # do this if we have to!
                self._cond.notify_all()

    def stop(self, timeout: Optional[float] = None) -> bool:
        """Shut down the semaphore.

        All pending and future calls to get will fail immediately. This function will then
        block until either the timeout elapses, or all active resources have been released by their
        holders.

        Args:
            timeout: How long to wait for a full shutdown, or None to wait forever.

        Returns:
            True if the semaphore has been shut down, False for a timeout.
        """

        with self._lock:
            self._stopped = True
            self._cond.notify_all()
            return self._cond.wait_for(lambda: self._current == 0, timeout=timeout)

    def set_capacity(self, capacity: Optional[int]) -> None:
        """Modify the capacity of the semaphore.

        Note that the current usage of the semaphore may be transiently greater than its capacity,
        if you reduce the capacity with this mechanism!
        """
        with self._lock:
            assert not self._stopped
            big_delta = self._capacity is not None and (
                capacity is None or (capacity - self._capacity) > 1
            )
            self._capacity = capacity
            # Same reasoning as inside release().
            if big_delta:
                self._cond.notify_all()
            else:
                self._cond.notify()

    class Status(NamedTuple):
        capacity: Optional[int]
        current: int
        stopped: bool

    @property
    def status(self) -> Status:
        """Fetch the current capacity, usage, and stop state."""
        with self._lock:
            return self.Status(self._capacity, self._current, self._stopped)

    class Resource(AbstractContextManager):
        def __init__(
            self,
            sem: "Semaphore",
            amount: int = 1,
            timeout: Optional[float] = None,
            check: bool = False,
        ) -> None:
            """Context manager to grab a resource from a semaphore.

            Create these with ``Semaphore.get()``.

            You have only acquired the resource if self.status == SUCCESS; remember to check the
            (bool) value of this context manager before using it!
            """
            self.sem = sem
            self.amount = amount
            if check:
                self.sem.acquire_checked(self.amount, timeout=timeout)
                self.status = Semaphore.AcquireResult.SUCCESS
            else:
                self.status = self.sem.acquire(self.amount, timeout=timeout)

        def __enter__(self) -> "Semaphore.Resource":
            return self

        def __exit__(
            self,
            exc_type: Optional[Type[BaseException]],
            exc_value: Optional[BaseException],
            traceback: Optional[TracebackType],
        ) -> None:
            if self.status == Semaphore.AcquireResult.SUCCESS:
                self.sem.release(self.amount)

        def __bool__(self) -> bool:
            return self.status == Semaphore.AcquireResult.SUCCESS

    def get(
        self, amount: int = 1, timeout: Optional[float] = None, check: bool = False
    ) -> Resource:
        """Context manager API to acquire capacity from the semaphore.

        This function works just like ``acquire()`` or ``acquire_checked()``, but (if it doesn't
        raise) returns a context manager which releases the resources on exit.

        If you call this with check=False, note that you **must** check whether the acquire
        succeeded (with ``resource.status``) before using it!

        Args:
            amount: The amount of capacity to acquire, which must be >= 0.
            timeout: How long we should block, in seconds, or None (the default) to wait forever.
                If the argument is zero, it is guaranteed that this function will not block.
            check: If True, this function will raise an exception on failure. If False, returns
                a resource with a nonzero status.

        Returns:
            A context manager whose bool value indicates whether the resource was successfully
                acquired or not. If check is True, this value is guaranteed to always be True.

        Raises:
            TimeoutError: If check=True, timeout != None, and the request timed out. This is a
                retriable error.
            BrokenPipeError: If check=True and the semaphore was stopped before the acquisition
                could complete. This is a non-retriable error.
        """
        return self.Resource(self, amount=amount, timeout=timeout)

    def __enter__(self) -> None:
        """The 'simple' context manager API, which grabs one unit and raises on failure.

        This is the most common case, and lets you simply say ``with semaphore:`` when every request
        should wait until it can grab one unit of capacity.

        Raises:
            BrokenPipeError: If the sempahore is stopped before the acquisition could complete.
        """
        self.acquire_checked()

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        # Note that we can only get here if we called Semaphore.__enter__, rather than
        # Resource.__enter__, so we know that the amount acquired was 1.
        self.release()
