import signal
import sys
import threading
import unittest
from types import FrameType
from typing import List, Optional

from pyppin.file.memfile import MemFile
from pyppin.threading.periodic_task import PeriodicTask


class PeriodicTaskTest(unittest.TestCase):
    def setUp(self) -> None:
        self.ops: List[str] = []
        self.time: float = 100.0
        self._stderr = MemFile()
        sys.stderr = self._stderr.open("w", buffering=1)  # type: ignore

    def tearDown(self) -> None:
        sys.stderr = sys.__stderr__

    def clock(self) -> float:
        """A clock function we can pass to tasks."""
        return self.time

    @property
    def stderr(self) -> str:
        return self._stderr.bytes.decode("utf8")

    def testPeriodicFunction(self) -> None:
        bell = threading.Event()

        def periodic() -> None:
            self.ops.append(f"Ran at {int(self.time)}")
            bell.set()

        task = PeriodicTask(
            periodic, period=20, wait_for_first=True, _test_clock=self.clock
        )
        self.assertEqual(["Ran at 100"], self.ops)
        self.assertTrue(bell.is_set())
        bell.clear()

        # This shouldn't cause it to run again.
        self.time = 110
        task._test_poke(expect_run=False)
        self.assertEqual(["Ran at 100"], self.ops)

        self.time = 120
        task._test_poke(expect_run=True)
        bell.wait()
        bell.clear()
        self.assertEqual(["Ran at 100", "Ran at 120"], self.ops)

        self.time = 145
        task._test_poke(expect_run=True)
        bell.wait()
        bell.clear()
        self.assertEqual(["Ran at 100", "Ran at 120", "Ran at 145"], self.ops)

        task.cancel()
        self.assertEqual(["Ran at 100", "Ran at 120", "Ran at 145"], self.ops)

    def testExceptions(self) -> None:
        def periodic() -> None:
            self.ops.append(f"Ran at {int(self.time)}")
            raise ValueError("Oh no, a failure!")

        with PeriodicTask(periodic, period=10, wait_for_first=True):
            self.assertEqual(["Ran at 100"], self.ops)
            self.assertTrue(self.stderr.endswith("ValueError: Oh no, a failure!\n"))

    def testExceptionDeath(self) -> None:
        def periodic() -> None:
            self.ops.append(f"Ran at {int(self.time)}")
            raise ValueError("Oh no, a failure!")

        def onsignal(signum: int, frame: Optional[FrameType]) -> None:
            self.ops.append(f"Got signal {signum}")

        # We'll use SIGFPE because it's one of the few that's defined on all systems.

        try:
            old_handler = signal.signal(signal.SIGFPE, onsignal)
            task = PeriodicTask(
                periodic,
                period=10,
                wait_for_first=True,
                die_on_exception=True,
                death_signal=signal.SIGFPE,
            )
            self.assertEqual(["Ran at 100", f"Got signal {signal.SIGFPE}"], self.ops)
            self.assertTrue(self.stderr.endswith("ValueError: Oh no, a failure!\n"))
            task.cancel()

        finally:
            signal.signal(signal.SIGFPE, old_handler)
