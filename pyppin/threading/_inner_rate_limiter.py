import math
import threading
import time
from abc import ABC
from typing import Optional

from pyppin.threading._rate_limiter_calibration import RateLimiterCalibration

# You need to use the monotonic clock, or (for obvious reasons) there's no guarantee anything will
# work right. This is also the clock used internally by threading.Lock.
CLOCK = time.monotonic


class InnerRateLimiter(ABC):
    """An abstract class for truly "inner" rate limiters.

    These have a more complex API than ordinary rate limiters, splitting their wait function into
    two calls:
        start_wait() does the actual blocking
        finish_wait() updates the internal state and releases the lock.
    These are separate because multi-layer rate limiters need to call them in a nested way: you
    start_wait on all the limiters, from coarsest to finest, to get the precise delay you want, and
    then you finish_wait in reverse order, because it's the timestamp of the _final_ limiter to
    finish that needs to be used in everyone else's "when did this actually happen" log.

    These functions hold the lock *between* them, so it's the caller's responsibility to ensure that
    every start_wait call is balanced by a finish_wait, even in the presence of exceptions. This is
    a scary and complicated API, and that's why this lives in a file whose name begins with an
    underscore.
    """

    def start_wait(self) -> float:
        """Start the wait operation.

        Delay until this limiter believes it is safe to proceed, and return the current time at
        which this was safe, per CLOCK.

        This function may modify the internal state of the limiter, including by holding a lock; it
        is required that the caller ensure that this call is always balanced by a call to
        finish_wait.
        """
        ...

    def finish_wait(self, timestamp: Optional[float]) -> float:
        """Finish the wait operation.

        It must be safe to call this function, even if start_wait was not called before. (That's
        because start_wait could be interrupted in arbitrarily messy ways)

        Args:
            timestamp: Either the timestamp (as returned by start_wait or CLOCK) at which the
            operation actually was permitted, or None to indicate that the wait operation failed and
            no operation is going to happen.

        Returns:
            The timestamp recorded for this item.
        """
        ...

    def wait(self) -> float:
        """A complete "wait", in case it's ever needed."""
        when: Optional[float] = None
        try:
            self.acquire()
            when = self.start_wait()
        finally:
            self.finish_wait(when)

        return when if when is not None else CLOCK()

    def set_rate(self, rate: float) -> None:
        """Set the rate of this limiter.

        Rate must be >= 0.
        """
        ...

    @property
    def rate(self) -> float:
        """Return the actual rate set on this limiter."""
        ...


class DelayRateLimiter(InnerRateLimiter):
    def __init__(self, calibration: RateLimiterCalibration) -> None:
        """This is an inner rate limiter that works by simply waiting until the relevant amount of
        time has passed between events. It's great at preventing overshoots, but it tends to
        undershoot hard at high rates, which is why it's only used at small rates.
        """
        self.calibration = calibration
        # The inverse rate is the delay between releases.
        self.inverse_rate: Optional[float] = None
        self.lock = threading.Lock()
        self.attn = threading.Condition(self.lock)
        self.last_release: float = 0

    def start_wait(self) -> float:
        self.lock.acquire()
        # We put this in a while loop because the rate may change, forcing us to restart.
        while True:
            if self.inverse_rate is None:
                self.calibration.delay(self.attn, None)
            else:
                now = CLOCK()
                delay = (self.last_release + self.inverse_rate) - now
                if delay <= 0:
                    return now
                self.calibration.delay(self.attn, delay)

    def finish_wait(self, timestamp: Optional[float]) -> float:
        # assert self.lock.locked()
        if timestamp is not None:
            self.last_release = timestamp
        try:
            self.lock.release()
        except RuntimeError:
            pass  # Don't freak out if the lock wasn't held.

    def set_rate(self, rate: float) -> None:
        assert rate >= 0
        with self.lock:
            self.inverse_rate = 1 / rate if rate > 0 else None
            self.attn.notify()

    @property
    def rate(self) -> float:
        return 1 / self.inverse_rate if self.inverse_rate is not None else 0


class IntervalRateLimiter(InnerRateLimiter):
    def __init__(self, calibration: RateLimiterCalibration, min_interval: float) -> None:
        """This is the "inner" implementation of RateLimiter.

        A real RateLimiter uses a few of these, nested. Unlike the "outer" one, which has a nice
        simple "rate" parameter of events per second, this one uses the underlying parameters of a
        interval size (in seconds) and a maximum number of events per interval. Thus the effective
        rate is count/interval, but picking the right interval size can lead to way more efficient
        waits.

        Args:
            calibration: The calibration parameters for this machine.
            min_interval: The shortest interval time we'll deliberately set.
        """
        self.calibration = calibration
        self.min_interval = min_interval
        self.lock = threading.Lock()
        self.attn = threading.Condition(self.lock)
        # The following variables are guarded by self.lock.
        self.interval = self.min_interval
        self.count = 0
        # The times of the most recent <count> releases. Its length is <= self.count.
        # TODO: Python lists have no 'reserve' operation, which could cause unpredictable CPU spikes
        # when we append to the array. Figure out a way around this if it becomes an issue.
        self.times: list[float] = []

    def set_rate(self, rate: float) -> None:
        """Set the rate from a numeric value, picking the right values of interval and count."""
        self._set_interval_and_count(*self._interval_and_count(rate))

    def _set_interval_and_count(self, interval: float, count: int) -> None:
        """The actual mechanism of setting the rate. This is a low-level mechanism and will allow
        you to set any positive interval, not just one limited by self.min_interval.
        """
        with self.lock:
            assert interval > 0
            assert count >= 0
            if count < len(self.times):
                self.times = self.times[-count:]
            self.count = count
            self.interval = interval
            self.attn.notify()

    def _interval_and_count(self, rate: float) -> tuple[float, int]:
        """Given a rate that we want to set on this limiter, return the appropriate
        interval and count settings.
        """
        if rate == 0:
            # Stopped case: Just pick a small interval time, and set the rate to zero per
            # interval.
            return (self.min_interval, 0)
        elif rate < 1 / self.min_interval:
            # Common case: The rate is low enough that 'one per interval' behavior works.
            return (1 / rate, 1)
        else:
            # We'll boost interval to MIN_INTERVAL + Δ, where Δ is picked so that the resulting
            # count is an integer. float_count is what the count would be if we just picked the
            # interval as MIN_INTERVAL
            float_count = rate * self.min_interval
            interval = self.min_interval + (math.ceil(float_count) - float_count) / rate
            count = int(rate * interval)
            return (interval, count)

    # Unlike the higher-level rate limiters, waiting is broken into two operations here: start_wait,
    # which does the blocking, and finish_wait, which updates the time queue. The lock is *left held
    # between these two operations*; these are separated because in the multi-layered rate limiter,
    # the calls need to be nested in order to work right. (You wait on the coarsest lock first, then
    # on successively finer locks to get the time as right as possible; but it's the timestamp from
    # the innermost of these locks that needs to be recorded)
    # It is therefore the responsibility of the caller to ensure that calls to start_ and
    # finish_wait are balanced.
    # (If you've ever implemented a mutex, you'll recognize similar behavior in the trans_ and _fer
    # methods. If you want to see how that works, I suggest looking at the Abseil C++ mutex
    # implementation, which is one of the classics. It will also remind you why mutex is one of the
    # Three Terrifying Functions -- along with memcpy and sort -- that even very experienced
    # professionals shy away from implementing.)

    def start_wait(self) -> float:
        self.lock.acquire()
        while True:
            now = CLOCK()
            next_release = self._prune_times(now)

            if len(self.times) < self.count:
                return now
            else:
                self.calibration.delay(
                    self.attn, next_release - now if next_release is not None else None
                )

    def finish_wait(self, timestamp: Optional[float]) -> float:
        # A None value of timestamp means we aborted.
        # assert self.lock.locked()
        if timestamp is not None:
            self.times.append(timestamp)
        try:
            self.lock.release()
        except RuntimeError:
            pass  # Don't freak out if the lock wasn't held.

    def _prune_times(self, now: float) -> Optional[float]:
        """Prune all no-longer-relevant elements of self.times. (i.e. events before threshold)

        Return the next value of 'now' at which this function will do something nontrivial, or None
        if it will never do so until something external changes.

        Requires self.lock to be held.
        """
        if not self.times:
            return None

        # assert self.lock.locked()
        threshold = now - self.interval
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

        return self.times[0] + self.interval if self.times else None

    @property
    def rate(self) -> float:
        # Deliberately don't grab the lock! I know these variables are protected, but this is a
        # classic "harmless race" -- the call to rate() can't expect a clear output if it's called
        # concurrently with set_rate() -- and waiting for the lock to release could literally take
        # forever.
        return self.count / self.interval


MIN_INTERVALS = [0.1, 0.01]


class MultiLayerRateLimiter(object):
    def __init__(self, calibration: RateLimiterCalibration) -> None:
        # Our stack of rate limiters, ordered from coarsest to finest. We use a delay rate limiter
        # at the very end to smooth out situations where we would need an impractically small
        # interval.
        self.limiters: list[IntervalRateLimiter] = [
            IntervalRateLimiter(calibration, interval) for interval in MIN_INTERVALS
        ] + [DelayRateLimiter(calibration)]
        # The number of limiters we're using at the moment, from 1 to len(self.limiters).
        self.num_in_use = 1

    def set_rate(self, rate: float) -> None:
        """Change the rate of this throttle."""
        assert rate >= 0
        original_rate = rate

        self.num_in_use = 0

        for index, limiter in enumerate(self.limiters):
            self.num_in_use += 1
            if isinstance(limiter, IntervalRateLimiter):
                limiter.set_rate(rate)
                print(
                    f'Rate layer {index}: Rate {rate} => {limiter.count} per {limiter.interval}, '
                    f'calc rate {limiter.rate}'
                )
                # If we've got an interval rate limiter with a count of 1, it can do even very
                # fine-grained rate limitation on its own, and we can stop here without any more
                # refinement.
                if limiter.count == 1:
                    break

                # The purpose of each successive subinterval is to smooth rates, not to do any
                # further throttling -- the outer interval on its own suffices for that. So we
                # increase the rate as we go deeper, so that successive limiters don't actually
                # slow down the operation of anything further out by accident.
                rate *= 1.05

            elif isinstance(limiter, DelayRateLimiter):
                # If we get here, we were having counts > 1 at all the coarser rate limiters, so
                # we'll use a simple time-delay.
                limiter.set_rate(original_rate)
                print(
                    f'Rate layer {index}: Rate {original_rate} means delay {limiter.inverse_rate} '
                    f'calc rate {limiter.rate}'
                )

        print(f'Using {self.num_in_use} layers')

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
        finally:
            for limiter in reversed(self.limiters[: self.num_in_use]):
                limiter.finish_wait(timestamp)

        # The 'else' case could only happen if num_in_use was zero, but it's good to handle that
        # deliberately.
        return timestamp if timestamp is not None else CLOCK()

    @property
    def rate(self) -> float:
        return self.limiters[0].rate
