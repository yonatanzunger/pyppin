import importlib
import math
import random
import threading
from time import monotonic, sleep
from typing import Any, Callable, List, NamedTuple, Tuple

from pyppin.math import minmax
from pyppin.math.histogram import Bucketing, Histogram

"""Calibration functions for the rate limiter.

The inner loop of the rate limiter needs to wait "for a given duration." If it waits for too short a
time, it will go back into the loop and basically waste CPU; but if it waits for too long a time, it
will undershoot, i.e. the real rate will be lower than the user-selected parameter. The challenge is
that the functions that "wait for a given duration" don't actually behave the way you might think
they do.

Roughly, there are three things we can do: spin, yield, and sleep. Spin means to continue the loop
without any intervening call; the time it takes to do that is tied to the performance of the Python
interpreter. Yield means that we explicitly yield the CPU so that other threads are allowed to run,
and then return to the calling thread.¹ Sleeping, in this case, means that we will use a condition
variable wait with a timeout. The question is, when do we use which, and if we use wait, what
argument do we pass to get the desired wait behavior when a timeout is likely?

Let's start from the top. If we measure the actual time waited when threading.Condition.wait(X) is
called and hits its timeout (which is the common case in a rate limiter), this turns out to be
linear in X if X is above some threshold, and then sharply above linear, converging to a constant,
below that threshold. The function calibrate_wait() measures the threshold and the linear fit
parameters (slope and intercept) above it.

Below that threshold, wait is a fairly slow pause, and we instead yield or spin. We measure the 90th
percentile times to spin and yield, the latter in both single- and multi-threaded environments. If
we are above 2x the yield time, we yield; if the wait we need is below even that, we spin.

The calibration function is somewhat nontrivial and requires the scipy library to be available. We
*don't* make it an ordinary pip dependency since most users of pyppin won't need this and it would
seriously bloat the dependencies if we did.

¹ It isn't particularly well-documented, but the Pythonic analogue of sched_yield() is
time.sleep(0).
"""


class RateLimiterCalibration(NamedTuple):
    """The calibration parameters of a rate limiter."""

    spin_interval: float
    """The typical time it takes to spin. The reciprocal of this is the rate limiter's best guess of
    the fastest speed it can maintain.
    """

    yield_threshold: float
    """The threshold time below which yield doesn't work robustly, and we should spin.

    Usually estimated as the 90th percentile yield time with 10 threads of contention.
    """

    wait_threshold: float
    """The threshold duration above which threading.Condition.wait is linear in its argument."""

    def delay(self, condition: threading.Condition, timeout: float) -> None:
        """Delay for approximately <timeout> seconds, minimizing overshot.

        The condition variable must be locked; by default, this function is equivalent to a wait on
        the condition.
        """
        if timeout >= self.wait_threshold:
            condition.wait(timeout=timeout)
        elif timeout >= self.yield_threshold:
            sleep(0)
        # Otherwise spin by simply returning!

    @property
    def max_rate(self) -> float:
        """Return our best estimate of the max rate this machine can support."""
        # XXX This is wrong -- the limit on our time is going to be way slower than this!!
        return 0.9 / self.spin_interval


WILD_ASS_GUESS = RateLimiterCalibration(
    spin_interval=1e-6, yield_threshold=2e-6, wait_threshold=2e-4
)

# A few special calibrations that we use while doing the calibrations themselves, so that we're
# testing our "real" delay functions.

_ALWAYS_SPIN = RateLimiterCalibration(
    spin_interval=0, yield_threshold=1e9, wait_threshold=1e9
)

_ALWAYS_YIELD = RateLimiterCalibration(
    spin_interval=0, yield_threshold=0, wait_threshold=1e9
)

_ALWAYS_WAIT = RateLimiterCalibration(
    spin_interval=0, yield_threshold=0, wait_threshold=0
)


_YIELD_PERCENTILE: float = 90


def calibrate(verbose: bool = True) -> RateLimiterCalibration:
    # Do this first, so that we can fail fast.
    try:
        importlib.import_module("scipy")
        importlib.import_module("numpy")
    except ModuleNotFoundError:
        raise ModuleNotFoundError(
            "Calibrating a rate limiter requires that scipy and numpy be available. This is not "
            "part of the pyppin dependency stack to avoid bloating it; if you need to use this "
            "function, please add both as dependencies to the calling code separately."
        )

    _print: Callable[[Any], None] = print if verbose else lambda x: None  # type: ignore

    _print("Calibrating rate limiter: Measuring spins")
    spin_times = calibrate_spin(num_threads=1, verbose=verbose)
    _print("  Measured spin times:")
    _print(spin_times.plot_ascii(max_percentile=_YIELD_PERCENTILE))
    spin_interval = 1e-9 * spin_times.median
    _print(f"  Estimated spin interval: {1e6 * spin_interval}μsec")

    _print("  Measuring yields")
    yield_times = calibrate_yield(num_threads=10, iterations=200000, verbose=verbose)
    _print("  Measured yield times:")
    _print(yield_times.plot_ascii(max_percentile=_YIELD_PERCENTILE))
    yield_threshold = 1e-9 * yield_times.percentile(_YIELD_PERCENTILE)
    _print(f"  Yield threshold: {1e6 * yield_threshold}μsec")

    _print("  Measuring waits")
    wait_threshold = calibrate_wait(num_threads=1, iterations=1000, verbose=verbose)
    _print(f"  Wait threshold: {1e6 * wait_threshold}μsec")

    return RateLimiterCalibration(
        spin_interval=spin_interval,
        yield_threshold=yield_threshold,
        wait_threshold=wait_threshold,
    )


def calibrate_spin(
    num_threads: int, iterations: int = 500000, verbose: bool = True
) -> Histogram:
    """Calibrate spin locking. Return a histogram in nanoseconds."""
    if verbose:
        print(f"Calibrating spin with {num_threads} threads")
    # Histogram in nsec.
    result = Histogram(
        bucketing=Bucketing(
            linear_steps=20,
            max_linear_value=400,
            exponential_multiplier=2,
        )
    )
    lock = threading.Lock()
    cond = threading.Condition(lock)
    start = threading.Barrier(num_threads + 1)

    def calibrate_spin_thread() -> None:
        """Measure the spin interval time within a single thread, and return the histogram of
        times measured.
        """
        times: List[float] = []
        start.wait()
        last = monotonic()
        for run in range(iterations):
            now = monotonic()
            # Technically we don't need to call delay here, but we do it to simulate reality as
            # closely as possible.
            _ALWAYS_SPIN.delay(cond, 0)
            times.append(now - last)
            last = now

        with lock:
            for time in times:
                result.add(time * 1e9)

    threads = [
        threading.Thread(target=calibrate_spin_thread) for index in range(num_threads)
    ]
    for thread in threads:
        thread.start()
    start.wait()
    for thread in threads:
        thread.join()

    return result


def calibrate_yield(
    num_threads: int, iterations: int = 50000, verbose: bool = True
) -> Histogram:
    """Calibrate yields. Return a histogram in microseconds."""
    if verbose:
        print(
            f"Calibrating yield with {num_threads} threads and {iterations} iterations/thread"
        )
    result = Histogram(
        bucketing=Bucketing(
            linear_steps=20,
            max_linear_value=400,
            exponential_multiplier=2,
        )
    )
    lock = threading.Lock()
    cond = threading.Condition(lock)
    start = threading.Barrier(num_threads + 1)

    def calibrate_yield_thread() -> None:
        """Measure the yield interval time within a single thread, and return the histogram of
        times measured.
        """
        times: List[float] = []
        start.wait()
        last = monotonic()
        for run in range(iterations):
            _ALWAYS_YIELD.delay(cond, 0)
            now = monotonic()
            times.append(now - last)
            last = now

        with lock:
            for time in times:
                result.add(time * 1e9)

    threads = [
        threading.Thread(target=calibrate_yield_thread) for index in range(num_threads)
    ]
    for thread in threads:
        thread.start()
    start.wait()
    for thread in threads:
        thread.join()

    return result


def calibrate_wait(
    num_threads: int = 1,
    iterations: int = 1000,
    log_min_duration: float = -7,
    log_max_duration: float = -1,
    verbose: bool = True,
) -> float:
    """Calibrate waits.

    Args:
        num_threads: The number of parallel threads to run.
        iterations: The number of iterations to run per thread.
        log_{min, max}_duration: The min and max input durations to test, as log10 of number of
            seconds.

    Returns:
        The minimum duration, in seconds, for which wait() can be trusted.
    """
    measurements = measure_wait(
        num_threads, iterations, log_min_duration, log_max_duration, verbose=verbose
    )
    return min_wait_time(measurements, verbose=verbose)


def measure_wait(
    num_threads: int = 1,
    iterations: int = 1000,
    log_min_duration: float = -7,
    log_max_duration: float = -1,
    verbose: bool = True,
) -> List[Tuple[float, float]]:
    """Calibrate waits.

    Wait calibration is different from yield and sleep calibration because wait operations take a
    parameter: we're looking for how closely the actual wait time tracks the requested wait time. In
    practice, we find that this is a very good correlation above a certain threshold (i.e., it
    matches a linear model with slope in the ballpark of 1) and a very lousy one beneath it (i.e. it
    deviates radically upwards)

    The calibration parameters we want are the lower bound for linear performance, and the slope and
    intercept of the fit parameters in the linear range.

    Args:
        num_threads: The number of parallel threads to run.
        iterations: The number of iterations to run per thread.
        log_{min, max}_duration: The min and max input durations to test, as log10 of number of
            seconds.

    Returns:
        A list of pairs of (requested, actual), where each pair element is the log10 of the time
        in seconds.
    """
    if verbose:
        print(
            f"Calibrating wait with {num_threads} threads and {iterations} iterations/thread"
        )
    result: List[Tuple[float, float]] = []
    lock = threading.Lock()
    cond = threading.Condition(lock)

    start = threading.Barrier(num_threads + 1)

    def calibrate_wait_thread() -> None:
        """Measure the spin interval time within a single thread, and return the histogram of
        times measured.
        """
        start.wait()
        with lock:
            for run in range(iterations):
                # Pick timeout. The shortest timeouts we want are in the ballpark of 1us, and the
                # longest 0.1s. So let's pick uniformly in the space of log(timeout), going from -6
                # to -1.
                log_timeout = random.uniform(log_min_duration, log_max_duration)
                timeout = math.pow(10, log_timeout)
                before = monotonic()
                # NB that we are never calling cond.notify, so the underlying call to cond.wait()
                # will *always* time out.
                _ALWAYS_WAIT.delay(cond, timeout)
                after = monotonic()
                result.append((log_timeout, math.log10(after - before)))

    threads = [
        threading.Thread(target=calibrate_wait_thread) for index in range(num_threads)
    ]
    for thread in threads:
        thread.start()
    start.wait()
    for thread in threads:
        thread.join()

    return result


def min_wait_time(
    data: List[Tuple[float, float]],
    verbose: bool = True,
) -> float:
    """Given (x, y) data from measure_wait, find the shortest input value for which wait() can
    be trusted.

    We approach this by slicing x-values (requested wait durations) into buckets. Within each bucket
    of roughly constant x, we assume that variation in y is shot (IID) noise, and compute the
    standard deviation in that bucket. What we see in practice is that above a certain threshold,
    these σ's converge to a (small) constant, but below that threshold, they start to shoot up
    rapidly. That threshold is the point where we stop trusting the wait function.
    """
    # Do the import first, so that we fail-fast if there's an error.
    optimize = importlib.import_module("scipy.optimize")
    numpy = importlib.import_module("numpy")

    num_windows = min(100, len(data) // 20)
    xmin, xmax = minmax(map(lambda x: x[0], data))
    window_size = (xmax - xmin) / num_windows

    def bucket(x: float) -> int:
        """Map an x-value to its bucket."""
        return math.floor((x - xmin) / window_size)

    num_buckets = bucket(xmax)

    # Calculate the actual standard deviations in each bucket.

    counts = [0] * num_buckets
    total = [0.0] * num_buckets
    total_squared = [0.0] * num_buckets
    for x, y in data:
        b = bucket(x)
        # Just xmax will be dropped here.
        if b < len(counts):
            counts[b] += 1
            total[b] += y
            total_squared[b] += y * y

    sigmas: List[float] = []
    for index in range(num_buckets):
        if not counts[index]:
            sigmas.append(1)
        else:
            mean = total[index] / counts[index]
            mean_sq = total_squared[index] / counts[index]
            sigmas.append(math.sqrt(mean_sq - mean * mean))

    # x_values should be evenly spaced between xmin and xmax.
    x_values = [xmin + (i / num_buckets) * (xmax - xmin) for i in range(num_buckets)]

    # We curve-fit to a roughly linear increase for small x, flipping over (fairly abruptly) to a
    # constant; thus, f(x) = b - a min(x, c). c is the point where the sigmas basically level off.
    (a, b, c), covariance = optimize.curve_fit(
        lambda x, a, b, c: b - a * numpy.minimum(x, c),
        x_values,
        sigmas,
        p0=(1, 1, -4),
    )
    t_critical = math.pow(10, c)

    if verbose:
        for index, effective_sigma in enumerate(sigmas):
            print(
                f"Bucket {index} from {index * window_size + xmin}: Sigma {effective_sigma}"
            )
        print(f"Noise seems to kick in at 10^{c:0.2f} = {t_critical} sec")

    return t_critical
