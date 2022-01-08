import threading
import time
from typing import Optional


class RateLimiter(object):
    """A throttle that limits the number of events that happen per unit time, across threads.

    The usage is simple: you have a single shared RateLimiter object, and each thread calls
    ``wait()`` when it is ready to perform an action. Those calls are guaranteed to unblock at a
    rate no greater than (and as close as possible to) the current rate set for the object. This is
    splendidly useful for managing load on a server, running loadtests at a fixed rate, etc.

    Args:
        rate: The initial rate, in events per second.
    """

    def __init__(self, rate: float = 0) -> None:
        """Construct a rate limiter."""

        # IMPLEMENTATION EXPLANATION
        # The RateLimiter class has an "inner" and an "outer" part. The inner part works as you
        # might expect: it has a lock (inner_lock) and condition variable, tracks the interval it
        # expects between successive events (self.interval) and the time of the most recent event
        # that happened. In wait(), we simply block on the condition variable until the current time
        # goes past previous time + interval.
        #
        # However, that simple implementation doesn't actually work very well. The problem is
        # contention: if there are a lot of threads, or a high rate, the mutex is getting a *lot* of
        # contention. This drives CPU usage through the roof, and causes the rate limiter to
        # underperform (i.e. release slower than) its intended rate. Worse, it breaks all the
        # fairness guarantees you usually expect of a waiter or a mutex, because each thread keeps
        # grabbing and releasing the lock every (short time interval), which effectively randomly
        # reshuffles the wait order every few microseconds.
        #
        # All of this is fixed by adding a second layer around it, a second mutex called the
        # "scheduling lock." Waiters grab the scheduling lock, and are only allowed to grab the
        # inner lock if they already hold the scheduling lock. This causes the waiters to queue up
        # on the scheduling lock *without* constantly grabbing and releasing it, so they form a
        # nice, orderly, low-CPU-usage queue, and only the waiter at the "head of the line" actually
        # does the regular grab-and-release of the inner lock.
        #
        # In a fun bit of nuance, though, this code does *not* use ordinary mutex theory. In
        # particular, there isn't an ordering relationship sched_lock > inner_lock; the rate and
        # set_rate functions grab inner_lock directly. They need to do this, because if they had to
        # wait in the scheduling queue it could take arbitrarily long to change the rate (even
        # infinitely long, if the rate is currently 0!). This doesn't cause a priority-inversion
        # deadlock because nobody who holds inner_lock can ever attempt to acquire sched_lock.
        self.sched_lock = threading.Lock()

        self.inner_lock = threading.Lock()
        # The following fields are guarded by self.inner_lock:
        self.cond = threading.Condition(self.inner_lock)
        self.interval: Optional[float] = 1.0 / rate if rate > 0 else None
        self.previous: float = 0

        # This is provided for unittests to inject their own clock. Don't mess with this outside of
        # the rate limiter test, it is subtle and quick to anger. (Subtle because you can't actually
        # inject a clock into threading.Condition.wait, so changing this doesn't do what you naively
        # may expect!)
        self._clock = time.monotonic

    def wait(self) -> float:
        """Block until it is safe to proceed.

        It is guaranteed that calls to wait() will unblock at a rate no greater than once every
        <rate> seconds, even when many threads are calling it.

        Returns: The time (per the monotonic clock) at which the wait released.
        """
        with self.sched_lock:
            with self.inner_lock:
                while True:
                    if self.interval is None:
                        self.cond.wait()
                    else:
                        next_release = self.previous + self.interval
                        now = self._clock()
                        if next_release <= now:
                            self.previous = now
                            return now
                        # TODO: Profile whether it would make more sense to call time.sleep(0) for
                        # sufficiently small intervals. This makes a big difference in C++ where a
                        # condvar wait is more expensive than sched_yield, but may not matter in
                        # Python.
                        self.cond.wait(timeout=next_release - now)

    @property
    def rate(self) -> float:
        """Return the current rate of this throttle."""
        with self.inner_lock:  # Could actually be a read lock
            return 1.0 / self.interval if self.interval is not None else 0

    def set_rate(self, rate: float) -> None:
        """Change the rate of this throttle."""
        assert rate >= 0
        with self.inner_lock:
            self.interval = 1.0 / rate if rate > 0 else None
            self.cond.notify()
