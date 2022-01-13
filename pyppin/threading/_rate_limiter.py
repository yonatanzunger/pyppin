import threading
from time import monotonic
from typing import List

from pyppin.math.histogram import Bucketing, Histogram


def calibrate_spin(num_threads: int, iterations: int = 50000) -> Histogram:
    """Calibrate spin locking."""
    # Histogram in nsec.
    result = Histogram(
        bucketing=Bucketing(
            linear_steps=20,
            max_linear_value=400,
            exponential_multiplier=2,
        )
    )
    lock = threading.Lock()
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


# Spin 1 thread -- 175ns
