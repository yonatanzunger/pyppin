import threading
import unittest
from time import monotonic, sleep
from typing import List, NamedTuple, Optional, Tuple, Union

from pyppin.base import assert_not_none
from pyppin.threading.rate_limiter import RateLimiter

# OK, what's the guarantee that we want to ensure? The underlying idea is that if I set a rate of X,
# and fire RPC's into something, it won't overload that thing. That thing might have spikiness
# constraints as well; really, a rate limit constraint on the server is the number of requests it
# can be dealing with concurrently, which comes from the request service time and parallelism. But
# you may or may not know those two parameters; instead, what you want is a more or less steady flow
# of requests, optimally one event every 1/rate seconds.


class RateLimiterTest(unittest.TestCase):
    class WorkerEvent(NamedTuple):
        time: float
        worker: int

    class RateChangeEvent(NamedTuple):
        rate: Optional[float]  # None for stop
        time: float

    def _exec_test(self, rates: List[RateChangeEvent], num_threads: int) -> List[WorkerEvent]:
        """Execute a single test.

        Args:
            rates: The sequence of which rates to set at which time.
            num_threads: The number of worker threads to use.;

        Returns:
            A list of worker events. NB that the base value of times is arbitrary in the resulting
            array.
        """
        assert num_threads > 0

        throttle = RateLimiter()
        startup = threading.Barrier(num_threads + 1)
        time_lock = threading.Lock()
        times: List[RateLimiterTest.WorkerEvent] = []
        stop = False

        def worker(index: int) -> None:
            history: List[float] = []

            startup.wait()
            # Technically there's a racy read here, but since stop is only written once and it
            # doesn't matter if we're late on picking it up, it's fine.
            while not stop:
                history.append(throttle.wait())

            with time_lock:
                times.extend(RateLimiterTest.WorkerEvent(time, index) for time in history)

        # Start up the worker threads
        threads = [threading.Thread(target=worker, args=(num,)) for num in range(num_threads)]
        for thread in threads:
            thread.start()

        print(f"Starting rate limiter test with {num_threads} threads")
        for rate in rates:
            if rate.rate is None:
                print(f"  Stop at {rate.time:0.2f}")
            else:
                print(f"  Rate {rate.rate} at {rate.time:0.2f}")

        # Run the master controller from this thread.
        startup.wait()
        start = monotonic()
        for rate in rates:
            while True:
                next = start + rate.time
                now = monotonic()
                if next <= now:
                    break
                sleep(next - now)

            # print(f"CONTROLLER SET RATE {rate} AT {now - start}")
            if rate.rate is None:
                with time_lock:
                    stop = True
            else:
                throttle.set_rate(rate.rate)

        assert stop is True
        for thread in threads:
            thread.join()

        times.sort(key=lambda event: event.time)

        return times

    def _rate_change_events(self, rates: List[float], wait_secs: float) -> List[RateChangeEvent]:
        """Compute when to set the rate to what."""
        time = 0.0
        previous_interval: Optional[float] = None
        result: List[RateLimiterTest.RateChangeEvent] = []
        for rate in rates:
            result.append(self.RateChangeEvent(rate, time))
            time += (previous_interval or 0) + wait_secs
            previous_interval = 1.0 / rate if rate != 0 else None

        time += (previous_interval or 0) + wait_secs
        result.append(self.RateChangeEvent(None, time))

        return result

    def _compute_actual_rates(self, events: List[WorkerEvent]) -> List[RateChangeEvent]:
        """Convert a raw sequence of WorkerEvents into a list of (rate, time) tuples."""
        if len(events) < 2:
            return []
        result: List[RateLimiterTest.RateChangeEvent] = []
        previous = events[0]
        start = previous.time
        for event in events[1:]:
            dt = event.time - previous.time
            result.append(RateLimiterTest.RateChangeEvent(rate=1.0 / dt, time=event.time - start))
            previous = event

        return result

    def _compute_smoothed_actual_rates(
        self, events: List[WorkerEvent], smoothing_secs: float
    ) -> List[RateChangeEvent]:
        """Like _compute_actual_rates, but rates are smoothed as a moving average over the given
        number of seconds.
        """
        assert smoothing_secs > 0

        if len(events) < 2:
            return []

        result: List[RateLimiterTest.RateChangeEvent] = []
        previous = events[0]
        start = previous.time

        window_start_index = 1
        window_total_rate = 0.0

        for index, event in enumerate(events[1:], 1):
            dt = event.time - previous.time
            rate = 1.0 / dt

            # Add the new rate to the window, and prune off any events that have fallen off the
            # averaging window.
            window_total_rate += rate

            window_start_time = event.time - smoothing_secs
            while events[window_start_index].time < window_start_time:
                # Get the rate for this event
                old_dt = events[window_start_index].time - events[window_start_index - 1].time
                old_rate = 1.0 / old_dt
                window_total_rate -= old_rate
                window_start_index += 1

            window_size = index - window_start_index + 1
            average_rate = window_total_rate / window_size
            result.append(
                RateLimiterTest.RateChangeEvent(rate=average_rate, time=event.time - start)
            )

            # Leaving some commented-out print statements because if you ever have a problem with
            # this test, this is the debug statement you're really going to want.
            # print(
            #     f"At {event.time - start} rate {rate}; index {index} window start "
            #     f"{window_start_index} gives window_total_rate {window_total_rate} avg "
            #     f"{average_rate}"
            # )

            previous = event

        return result

    def _verify_rates(
        self,
        expected: List[RateChangeEvent],
        actual: List[RateChangeEvent],
        smoothed: List[RateChangeEvent],
        expected_decay_time: float,
    ) -> Tuple[bool, List[str]]:
        """Check that an actual set of rate changes matched the expectation.

        Return success, list of messages.
        """
        assert len(expected) >= 2
        assert len(actual) == len(smoothed)

        failed = False
        messages: List[str] = []

        # Slice up time based on expected. In each time window, track the previous and current
        # rates, and the start and end time of this window.
        window = 0
        previous_rate = 0.0
        current_rate = assert_not_none(expected[0].rate)
        window_start = expected[0].time
        window_end = expected[1].time

        messages.append(
            f"Initial window rate {current_rate:0.2f} from {window_start:0.2f} to "
            f"{window_end:0.2f}"
        )

        for event, smoothed_event in zip(actual, smoothed):
            assert event.rate is not None
            assert smoothed_event.rate is not None
            assert event.time == smoothed_event.time

            # Check if we need to move to a new window.
            if event.time > window_end:
                window += 1
                if window >= len(expected):
                    break
                elif window + 1 == len(expected):
                    self.assertIsNone(expected[window].rate)
                    window_start = expected[window].time
                    window_end = 100000000000000  # Bignum
                    messages.append(f"Final window started at {window_start:0.2f}")
                else:
                    previous_rate = current_rate
                    current_rate = assert_not_none(expected[window].rate)
                    window_start = expected[window].time
                    window_end = expected[window + 1].time
                    messages.append(
                        f"Window rate {current_rate:0.2f} from {window_start:0.2f} to "
                        f"{window_end:0.2f}"
                    )

            # Now let's see where we are relative to our expected rate.
            window_position = event.time - window_start

            # During the decay time, expect our rate to be between previous and current.
            if window_position < expected_decay_time:
                expected_max = max(previous_rate, current_rate)
                if event.rate > expected_max:
                    failed = True
                    percent = 100.0 * ((event.rate / expected_max) - 1)
                    messages.append(
                        f"At {event.time}: Rate {event.rate:0.2f} exceeded cap of "
                        f"{expected_max:0.2f} by {percent:0.1f}%"
                    )
            else:
                # Check for overshoots against the true (unsmoothed) rate, because overshooting even
                # on a single call to wait() is an error.
                if event.rate > current_rate:
                    failed = True
                    percent = 100.0 * ((event.rate / current_rate) - 1)
                    messages.append(
                        f"At {event.time}: Rate {event.rate:0.2f} exceeded cap of "
                        f"{current_rate:0.2f} by {percent:0.1f}%"
                    )
                # Check for undershoots against the smoothed rate, because we allow occasional
                # failures that way.
                if smoothed_event.rate < 0.9 * current_rate:
                    failed = True
                    percent = 100.0 * (1 - (smoothed_event.rate / current_rate))
                    messages.append(
                        f"At {event.time}: Rate {smoothed_event.rate:0.2f} undershot target of "
                        f"{current_rate:0.2f} by {percent:0.1f}%"
                    )

        return not failed, messages

    def parametrized_test(
        self,
        rate: Union[float, List[float]],
        num_threads: int,
        equilibriation_padding_secs: float = 0.5,
        max_undershot_secs: float = 0.1,
    ) -> None:
        """Run a single test run of the rate limiter.

        Args:
            rate: Either a float (the rate for the limiter) or a list of rates. If a list is
                passed, we'll run at one rate, let it equilibrate, move to the next rate, etc.
            num_threads: The number of threads to simultaneously wait on the limiter.
            equilibriation_padding_secs: Whenever we change the rate to X, we wait 1/X + this
                many seconds for the rate to reach equilibrium.
            max_undershot_secss: The number of seconds over which we do averaging to make sure that
                undershots we observe are "real." (We only do this for undershots: even a momentary
                overshot is a true error!)
        """
        if isinstance(rate, float):
            rate = [rate]

        rates = self._rate_change_events(rate, wait_secs=2 * equilibriation_padding_secs)
        times = self._exec_test(rates, num_threads)

        # OK! Now that we've run the test, let's compute rate as a function of time.
        # TODO: Also use times.worker to make fairness checks.

        real_rates = self._compute_actual_rates(times)
        smoothed_rates = self._compute_smoothed_actual_rates(times, max_undershot_secs)
        success, messages = self._verify_rates(
            rates, real_rates, smoothed_rates, equilibriation_padding_secs
        )
        if not success:
            if len(messages) > 20:
                messages = (
                    messages[:10] + [f'... {len(messages)-20} more messages...'] + messages[-10:]
                )
            raise AssertionError("\n  ".join(messages))

    def testSteadySlowRate(self) -> None:
        self.parametrized_test([20], 1)

    def testSteadyMediumRate(self) -> None:
        self.parametrized_test([100], 1)

    def testSteadyHighRate(self) -> None:
        self.parametrized_test([1000], 1)

    """

    def testSteadyHighRate(self) -> None:
        self.parametrized_test([40], 1)

    def testIncreasingRateOneThread(self) -> None:
        self.parametrized_test([10, 20, 30], 1)

    def testDecreasingRateOneThread(self) -> None:
        self.parametrized_test([30, 20, 10], 1)
    """
