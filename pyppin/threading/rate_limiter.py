import threading

# import time
from typing import Optional

from pyppin.threading._inner_rate_limiter import MultiLayerRateLimiter
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
        # The RateLimiter class has three layers: an inner rate limiter, a multi-layered rate
        # limiter, and an outer rate limiter.
        #
        # The inner rate limiter is the part that works the way you might naively expect. It doesn't
        # do the completely naive thing of remembering the time of the last wait() event and waiting
        # for (time + expected interval), because what we want to promise is average performance
        # over time, and that function would underperform; instead, it splits time into "intervals"
        # and ensures that no more than N events happen per time window I. In the simple case, N=1
        # and I=1/rate, but we bound I below and let N increase instead as a way to avoid huge
        # overloads when I is very small.
        #
        # The multi-layered middle phase simply takes a stack of inner rate limiters -- one that
        # ensures that the rate per time is R, and (if the interval is _coarse_ enough) one that
        # slices up the interval into subintervals, and ensures that the rate per subinterval is
        # bounded at the right rate. Otherwise, we'll get all the events per interval clustering
        # up at artificial interval boundaries, creating a very choppy output.
        #
        # The outer layer then optimizes all of this substantially by abusing mutex theory. One
        # problem with the design of the previous layers is that, if many threads are wanting to
        # execute, they will all simultaneously be hammering the mutices, and thus burn a lot of CPU
        # time on contention. But this is silly, because you know that only one of them is going to
        # go next. So in the outer layer, we add a second mutex called the "scheduling lock."
        # Waiters grab (i.e. enqueue on) the scheduling lock, and only the one who actually holds
        # the lock (i.e. the one at the front of the queue) is allowed to call wait() on the next
        # layer in. This guarantees that there's at most one concurrent call to wait(), and no
        # thread contention in the inner loop!
        #
        # The abuse of mutex theory is that, despite the presence of multiple locks, it is *not*
        # true that sched_lock > lock; in particular, the set_rate function grabs the inner lock
        # without touching the schedule lock. They need to do this, because if they had to wait in
        # the scheduling queue it could literally take forever to execute (if e.g. the current rate
        # were zero!) This doesn't cause a priority-inversion deadlock because nobody who holds the
        # inner lock can ever attempt to acquire the scheduling lock.
        self.sched_lock = threading.Lock()
        self.impl = MultiLayerRateLimiter(calibration or WILD_ASS_GUESS)
        self.set_rate(rate)

    def wait(self) -> float:
        """Block until it is safe to proceed.

        It is guaranteed that calls to wait() will unblock at a rate no greater than once every
        <rate> seconds, even when many threads are calling it.

        Returns: The time (per the monotonic clock) at which the wait released.
        """
        with self.sched_lock:
            return self.impl.wait()

    @property
    def rate(self) -> float:
        """Return the current rate of this throttle."""
        return self.impl.rate

    def set_rate(self, rate: float) -> None:
        """Change the rate of this throttle."""
        self.impl.set_rate(rate)

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
