import math
import threading
import time
from typing import Optional

from pyppin.threading._rate_limiter_calibration import RateLimiterCalibration


class InnerRateLimiter(object):
    # This is the "inner" implementation of RateLimiter. A real RateLimiter uses a few of these,
    # nested. Unlike the "outer" one, which has a nice simple "rate" parameter of events per second,
    # this one uses the underlying parameters of a window size (in seconds) and a maximum number of
    # events per window. Thus the effective rate is count/window, but picking the right window size
    # can lead to way more efficient waits.
    def __init__(self, calibration: RateLimiterCalibration) -> None:
        self.calibration = calibration
        self.clock = time.monotonic  # Exposed only for testing
        self.lock = threading.Lock()
        self.attn = threading.Condition(self.lock)
        # The following variables are guarded by self.lock.
        self.window = 1
        self.count = 0
        # The times of the most recent <count> releases. Its length is <= self.count.
        # TODO: Python lists have no 'reserve' operation, which could cause unpredictable CPU spikes
        # when we append to the array. Figure out a way around this if it becomes an issue.
        self.times: list[float] = []

    def set_rate(self, window: float, count: int) -> None:
        with self.lock:
            assert window > 0
            assert count >= 0
            if count < len(self.times):
                self.times = self.times[-count:]
            self.count = count
            self.window = window
            self.attn.notify()

    # Unlike the higher-level rate limiters, waiting is broken into two operations here: start_wait,
    # which does the blocking, and finish_wait, which updates the time queue. The lock is *left held
    # between these two operations*; these are separated because in the multi-layered rate limiter,
    # the calls need to be nested in order to work right. (You wait on the coarsest lock first, then
    # on successively finer locks to get the time as right as possible; but it's the timestamp from
    # the innermost of these locks that needs to be recorded)
    # It is therefore the responsibility of the caller to ensure that calls to start_ and
    # finish_wait are balanced.

    def start_wait(self) -> float:
        self.lock.acquire()
        while True:
            now = self.clock()
            next_release = self.prune_times(now)
            if len(self.times) < self.count:
                return now
            else:
                self.calibration.delay(self.attn, next_release - now)

    def finish_wait(self, timestamp: Optional[float]) -> float:
        # A None value of timestamp means we aborted.
        try:
            if timestamp is not None:
                self.times.append(timestamp)
        finally:
            self.lock.release()

    def wait(self) -> float:
        """Block until safe to proceed; return the release time."""
        self.finish_wait(self.start_wait())

    def prune_times(self, now: float) -> Optional[float]:
        """Prune all no-longer-relevant elements of self.times. (i.e. events before threshold)

        Return the next value of 'now' at which this function will do something nontrivial, or None
        if it will never do so until something external changes.

        Requires self.lock to be held.
        """
        if not self.times:
            return None

        # assert self.lock.locked()
        threshold = now - self.window
        # We are going to do a linear, not a bisecting, search because these arrays are typically
        # small and I don't trust the bisection algorithm not to thrash the L1 cache.
        for index, value in enumerate(self.times):
            if value >= threshold:
                # We've hit a value we want to keep!
                self.times = self.times[index:]
                break
        else:
            # If we get here, all the values were stale!
            self.times.clear()

        return self.times[0] + self.window if self.times else None

    @property
    def rate(self) -> float:
        # Deliberately don't grab the lock! I know these variables are protected, but this is a
        # classic "harmless race" -- the call to rate() can't expect a clear output if it's called
        # concurrently with set_rate() -- and waiting for the lock to release could literally take
        # forever.
        return self.count / self.window


class MultiLayerRateLimiter(object):
    def __init__(self, calibration: RateLimiterCalibration) -> None:
        self.calibration = calibration
        # Our stack of rate limiters, ordered from coarsest to finest.
        self.limiters: list[InnerRateLimiter] = [
            InnerRateLimiter(calibration),
            InnerRateLimiter(calibration),
        ]
        # The number of limiters we're using at the moment, from 1 to len(self.limiters).
        self.num_in_use = 1

    MIN_INTERVAL = 0.1  # Seconds -- roughly the smallest interval we ever want.
    INVERSE_MIN_INTERVAL = 1.0 / MIN_INTERVAL

    # The shortest possible time for a subinterval.
    MIN_SUBINTERVAL = 0.01

    def rate_to_interval_and_count(self, rate: float, min_interval: float) -> tuple[float, int]:
        """Convert a rate to an (interval, count) that's appropriate for it."""
        if rate == 0:
            # Stopped case: Just pick a small interval time, and set the rate to zero per interval.
            return (min_interval, 0)
        elif rate < 1 / min_interval:
            # Common case: The rate is low enough that 'one per interval' behavior works.
            return (1 / rate, 1)
        else:
            # We'll boost interval to MIN_INTERVAL + Δ, where Δ is picked so that the resulting
            # count is an integer. float_count is what the count would be if we just picked the
            # interval as MIN_INTERVAL
            float_count = rate * min_interval
            interval = min_interval + (math.ceil(float_count) - float_count) / rate
            count = int(rate * interval)
            return (interval, count)

    def set_rate(self, rate: float) -> None:
        """Change the rate of this throttle."""
        assert rate >= 0

        interval, count = self.rate_to_interval_and_count(rate, self.MIN_INTERVAL)
        print(f'Interval Rate {rate} => {count} per {interval} calc {count / interval}')
        self.limiters[0].set_rate(interval, count)

        # The subinterval's purpose is smoothing, not throttling, so we set its target rate above
        # our actual target rate, to make sure it doesn't accidentally slow us down.
        subinterval, subcount = self.rate_to_interval_and_count(1.1 * rate, self.MIN_SUBINTERVAL)

        # Now, do we also need a subinterval?
        if interval > self.MIN_INTERVAL * self.SUBINTERVALS:
            subinterval = interval / self.SUBINTERVALS
            subcount = (count + self.SUBINTERVALS - 1) // self.SUBINTERVALS
            print(f'Fine rate: {subcount} per {subinterval} calc {subcount / subinterval}')
            self.limiters[1].set_rate(subinterval, subcount)
            self.num_in_use = 2
        else:
            print('No fine throttle')
            self.num_in_use = 1

    def wait(self) -> float:
        # We need to do these nested calls, but we need to guarantee that we balance start/finish
        # calls even in the presence of exceptions. We can't use Python's context manager mechanism,
        # because that doesn't support runtime-defined depths of execution, so instead we'll do it
        # the old-fashioned way.
        timestamp: Optional[float] = None
        count_locked = 0
        try:
            for limiter in self.limiters[: self.num_in_use]:
                timestamp = limiter.start_wait()
                count_locked += 1
        except BaseException:
            for limiter in reversed(self.limiters[:count_locked]):
                limiter.finish_wait(None)
            raise
        else:
            for limiter in reversed(self.limiters[: self.num_in_use]):
                limiter.finish_wait(timestamp)

        # The 'else' case could only happen if num_in_use was zero, but it's good to handle that
        # deliberately.
        return timestamp if timestamp is not None else self.clock.now()

    @property
    def rate(self) -> float:
        return self.coarse.rate
