from contextlib import AbstractContextManager
from enum import Enum
from threading import Condition, Lock
from time import monotonic
from types import TracebackType
from typing import NamedTuple, Optional, Type


class Semaphore(object):
    def __init__(self, capacity: Optional[int] = None) -> None:
        """A semaphore, aka a shared reservoir of (integer) capacity.

        You can acquire some amount of resource from a semaphore, and it guarantees that no more
        than the current capacity will ever be simultaneously held. Acquisitions can specify a
        timeout for how long they want to wait for this to be true, or simply wait forever. Once you
        do acquire capacity, you are responsible for releasing it afterwards!

        The simple (context manager) way to get resource is with ``acquire()``; the low-level
        ``ll_acquire()`` and ``ll_release()`` methods let you directly grab resource without a
        context manager.

        Warning
        =======
        If a code unit (e.g. a thread, or a worker object that can move between threads) acquires
        capacity, it **must not** acquire any further capacity until it has first released what it
        holds. Otherwise you will get a thread-starvation deadlock,¹ which is notoriously hard to
        catch via static analysis or unittests, and only manifests in production under high load,
        when your program suddenly comes to a halt. If you might need more capacity later on in a
        process, acquire the maximum amount of capacity you might need *first* and release some
        later.

        ¹ The exact mechanism: Say a worker holds one unit of capacity, and wants to grab one more
        unit of capacity, do something, then release both. Now imagine that many identical workers
        are active at once, so that the semaphore is at capacity. Every one of the workers could
        release some capacity, allowing things to continue, if it could _just_ get one unit of
        capacity -- but there is none, and nobody can release any! The program deadlocks. This is
        especially insidious because the most common reason someone might accidentally do this is if
        workers only *sometimes* need that second unit of capacity. In that case, normally things
        work fine: even if one worker needs an extra unit, some other worker will soon finish its
        task (without needing that) and release capacity. Things only go wrong once there are enough
        workers simultaneously in that special state, which tends to happen in unpredictable
        circumstances but generally in the middle of the night or during a highly-visible public
        event. Don't let this happen to you. Release before you acquire.

        Args:
            capacity: The maximum value of concurrent capacity which can be used, or None for an
              infinite value. (This is still useful because you can ``wait()`` for it or monitor
              its ``status()``)
        """
        self._capacity = capacity
        self._current: int = 0
        self._stopped = False
        self._lock = Lock()
        self._cond = Condition(self._lock)

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

        UNKNOWN = 3
        """The acquire is in an unknown state, probably because you haven't tried to acquire yet."""

    class Resource(AbstractContextManager):
        def __init__(
            self, sem: "Semaphore", amount: int = 1, timeout: Optional[float] = None
        ) -> None:
            """Context manager to grab a resource from a semaphore.

            Create these with ``Semaphore.acquire()``.

            You have only acquired the resource if self.status == SUCCESS; remember to check the
            (bool) value of this context manager before using it!
            """
            self.sem = sem
            self.amount = amount
            self.timeout = timeout
            self.status = Semaphore.AcquireResult.UNKNOWN

        def __enter__(self) -> "Semaphore.Resource":
            self.status = self.sem.ll_acquire(self.amount, timeout=self.timeout)
            return self

        def __exit__(
            self,
            exc_type: Optional[Type[BaseException]],
            exc_value: Optional[BaseException],
            traceback: Optional[TracebackType],
        ) -> None:
            if self.status == Semaphore.AcquireResult.SUCCESS:
                self.sem.ll_release(self.amount)

        def __bool__(self) -> bool:
            return self.status == Semaphore.AcquireResult.SUCCESS

    def acquire(
        self, amount: int = 1, timeout: Optional[float] = None
    ) -> "Semaphore.Resource":
        """Acquire (take ownership of) some capacity within the semaphore.

        This is the preferred method to acquire capacity, since it returns a context manager that
        releases it for you when you're done. If you need to directly acquire capacity (and are OK
        with being responsible for releasing it afterwards, probably in a finally block) you can
        call ll_acquire() and ll_release() yourself.

        This function blocks until either the requisite amount of capacity becomes available, or the
        timeout is reached. It returns true if the capacity was successfully acquired, in which case
        the caller now owns this amount of capacity and MUST release() it.

        Args:
            amount: The amount of capacity to acquire, which must be >= 0.
            timeout: How long we should block, in seconds, or None (the default) to wait forever.
                If the argument is zero, it is guaranteed that this function will not block.

        Returns:
            A context manager whose value is a bool indicating whether the resource was successfully
                acquired or not. If timeout is None, it is guaranteed that this value is always
                True.
        """
        return self.Resource(self, amount=amount, timeout=timeout)

    def ll_acquire(
        self, amount: int = 1, timeout: Optional[float] = None
    ) -> "Semaphore.AcquireResult":
        """Acquire (take ownership of) some capacity within the semaphore.

        This is the low-level function to acquire capacity. If it returns true, the caller now owns
        `amount` of capacity and **must** release it, by calling ``ll_release()``, when they are
        done using it.

        Args:
            amount: The amount of capacity to acquire.
            timeout: How long we should block, in seconds. None (the default) means to wait
                forever. Zero means that we should never block; if we can't instantly acquire
                the capacity, return immediately.

        Returns:
            SUCCESS if the capacity was successfully acquired.
            TIMEOUT if the acquisition failed because time ran out.
            STOPPED if the acquisition failed because the semaphore has stopped. (This is a
            non-transient error!)
        """
        assert amount >= 0

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
                    if now >= deadline or not self._cond.wait(timeout=deadline - now):
                        return self.AcquireResult.TIMEOUT
                else:
                    self._cond.wait()

    def ll_release(self, amount: int = 1) -> None:
        """Release capacity acquired via ``ll_acquire()``."""
        with self._lock:
            assert self._current >= amount
            self._current -= amount
            self._cond.notify()

    def stop(self, timeout: Optional[float] = None) -> bool:
        """Shut down the semaphore.

        All pending and future calls to acquire will fail immediately. This function will then
        block until either the timeout elapses, or all active resources have been released by their
        holders.

        Args:
            timeout: How long to wait for a full shutdown, or None to wait forever.

        Returns:
            True if the semaphore has been shut down, False for a timeout.
        """

        with self._lock:
            self._stopped = True
            self._cond.notify()
            return self._cond.wait_for(lambda: self._current == 0, timeout=timeout)

    def set_capacity(self, capacity: Optional[int]) -> None:
        """Modify the capacity of the semaphore.

        Note that the current usage of the semaphore may be transiently greater than its capacity,
        if you reduce the capacity with this mechanism!
        """
        with self._lock:
            assert not self._stopped
            self._capacity = capacity
            self._cond.notify()

    class Status(NamedTuple):
        capacity: Optional[int]
        current: int
        stopped: bool

    def status(self) -> Status:
        """Fetch the current capacity, usage, and stop state."""
        with self._lock:
            return self.Status(self._capacity, self._current, self._stopped)
