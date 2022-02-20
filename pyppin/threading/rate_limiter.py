import threading
import time
from typing import Optional

from pyppin.threading._rate_limiter_calibration import (
    WILD_ASS_GUESS,
    RateLimiterCalibration,
    calibrate,
)


class RateLimiter(object):
    """A throttle that limits the number of events that happen per unit time, across threads.

    The usage is simple: you have a single shared RateLimiter object, and each thread calls
    ``wait()`` when it is ready to perform an action. Those calls are guaranteed to unblock at a
    rate no greater than (and as close as possible to) the current rate set for the object. This is
    splendidly useful for managing load on a server, running loadtests at a fixed rate, etc.

    Args:
        rate: The initial rate, in events per second.
        calibration: Optional calibration parameters. Without these, the rate limiter should
            function up to a rate of about 30, but will start to significantly underperform (i.e.,
            release from wait()s at a slower rate than you requested) above this. These parameters
            allow higher performance. See RateLimiter.calibrate() (below) for how to generate these.
    """

    def __init__(
        self, rate: float = 0, calibration: Optional[RateLimiterCalibration] = None
    ) -> None:
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

        self.calibration = calibration or WILD_ASS_GUESS

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
                        # The naive thing to do here would be to call self.cond.wait(), but this
                        # underperforms rather radically for short time intervals; basically, if you
                        # call that function with a short enough timeout, it will not time out
                        # nearly as quickly as you might expect from the function signature. So we
                        # use the calibrated delay function that is generally cleverer.
                        self.calibration.delay(
                            self.cond, timeout=RateLimiter._FUDGE_FACTOR * (next_release - now)
                        )

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

    @classmethod
    def calibrate(self) -> RateLimiterCalibration:
        """Run a calibration to determine the tuning parameters for this machine.

        Without calibration, the rate limiter may underperform at even fairly moderate (30qps)
        rates. The calibration values will be a function of your Python interpreter, your hardware
        platform, and pretty much anything else that affects the environment.

        This function takes several seconds to run, but its values can be stored and reused for
        later. Generally speaking, a good "cache key" for this would be a combination of
        sys.implementation, the OS version, and the particular hardware configuration; any
        change to one of those will require recalibration.
        """
        return calibrate()

    # We delay a bit less than the actual duration we want, because all the delay mechanisms tend to
    # undershoot by a *bit*. The main loop of wait() will then end up unblocking a few more times
    # than it needs to (to reduce the rate down to the actual target) but that simply guarantees
    # that we'll hit our actual targets.
    _FUDGE_FACTOR = 0.9
