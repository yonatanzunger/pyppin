import unittest
from typing import List

from pyppin.util.exponential_backoff import retry


class FakeSleep(object):
    def __init__(self) -> None:
        self.times: List[float] = []

    def __call__(self, duration: float) -> None:
        self.times.append(duration)


class ExponentialBackoffTest(unittest.TestCase):
    def test_fail_twice(self) -> None:
        counter = 0

        def fail_twice() -> int:
            nonlocal counter
            counter += 1
            if counter < 3:
                raise RuntimeError(f"Oh no! #{counter}")
            return 3

        sleep = FakeSleep()

        result = retry(fail_twice, retry=[RuntimeError], _sleep=sleep)
        self.assertEqual(3, result)
        self.assertEqual([0.1, 0.2], sleep.times)

    def test_max_attempts(self) -> None:
        def fail_forever() -> int:
            raise RuntimeError("Never works!")

        sleep = FakeSleep()
        with self.assertRaises(RuntimeError):
            retry(
                fail_forever,
                retry=[RuntimeError],
                max_attempts=5,
                max_delay=1,
                _sleep=sleep,
            )
        self.assertEqual([0.1, 0.2, 0.4, 0.8, 1], sleep.times)

    def test_nonretriable_error(self) -> None:
        counter = 0

        def fail_nonretriable() -> int:
            nonlocal counter
            counter += 1
            if counter == 1:
                raise RuntimeError("This is retriable")
            elif counter == 2:
                raise ValueError("This is not retriable")
            else:
                return 3

        sleep = FakeSleep()
        with self.assertRaises(ValueError):
            retry(fail_nonretriable, retry=[RuntimeError], _sleep=sleep)
        self.assertEqual([0.1], sleep.times)
