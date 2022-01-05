import threading
import unittest
from typing import List

from pyppin.threading.periodic_task import PeriodicTask


class PeriodicTaskTest(unittest.TestCase):
    def testPeriodicFunction(self) -> None:
        ops: List[str] = []
        time: float = 100.0
        bell = threading.Event()

        def clock() -> float:
            return time

        def periodic() -> None:
            ops.append(f"Ran at {int(time)}")
            bell.set()

        task = PeriodicTask(periodic, period=20, wait_for_first=True, _test_clock=clock)
        self.assertEqual(["Ran at 100"], ops)
        self.assertTrue(bell.is_set())
        bell.clear()

        # This shouldn't cause it to run again.
        time = 110
        task._test_poke(expect_run=False)
        self.assertEqual(["Ran at 100"], ops)

        time = 120
        task._test_poke(expect_run=True)
        bell.wait()
        bell.clear()
        self.assertEqual(["Ran at 100", "Ran at 120"], ops)

        time = 145
        task._test_poke(expect_run=True)
        bell.wait()
        bell.clear()
        self.assertEqual(["Ran at 100", "Ran at 120", "Ran at 145"], ops)

        task.cancel()
        self.assertEqual(["Ran at 100", "Ran at 120", "Ran at 145"], ops)

    # TODO test set_period
