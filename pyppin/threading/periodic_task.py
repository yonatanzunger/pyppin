"""Run a function periodically in a background thread."""

import signal
import sys
import threading
import time
import traceback
from datetime import timedelta
from types import TracebackType
from typing import Callable, Optional, Type, Union


class PeriodicTask(threading.Thread):
    """Execute ``function()`` at regular intervals in a background thread.

    Args:
        function: The function to be called.
        period: The interval between successive calls to the function, either as a timedelta
            or in seconds. Note that this is measured from the *start* of one call to the
            *start* of the next.
        name: The name for the thread, defaulting to the function name.
        wait_for_first: If true, the constructor will block until the first call to the
            function has finished.
        die_on_exception: If function raises an uncaught exception, we will always print
            the stack trace to stderr -- but what should we do next? Python doesn't propagate
            exceptions in child threads to the parent thread. If this flag is False, we do
            nothing, and simply call the function again next time. If it is True, we will
            instead kill the parent process on exception, providing a sort of simulacrum
            of what would have happened had this failed in the main thread.
        death_signal: The signal we will use to kill this process if die_on_exception is True.

    This class can also be used as a context manager, in which case it will cancel the periodic
    task once you exit the context.
    """

    def __init__(
        self,
        function: Callable[[], None],
        period: Union[timedelta, float],
        name: Optional[str] = None,
        wait_for_first: bool = False,
        die_on_exception: bool = False,
        death_signal: int = signal.SIGTERM,
        _test_clock: Optional[Callable[[], float]] = None,
    ) -> None:
        super().__init__(name=name or getattr(function, "__name__", None), daemon=True)
        self.function = function
        self.die_on_exception = die_on_exception
        self.death_signal = death_signal
        self.clock = _test_clock or time.monotonic
        self.first = threading.Event()  # Signals after the first run has finished.

        # self.lock protexts last, next, period, and stop.
        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)
        self.last: float = 0
        self.next: float = 0
        self.period: float = (
            period.total_seconds() if isinstance(period, timedelta) else period
        )
        assert self.period > 0
        self.stop = False
        # For testing: If this isn't None, it's what we expect to happen during the next pass
        # through the run loop.
        self._expect_run: Optional[bool] = None

        self.start()

        if wait_for_first:
            self.first.wait()

    def set_period(self, period: Union[timedelta, float]) -> None:
        """Change the period of the operation."""
        period = period.total_seconds() if isinstance(period, timedelta) else period
        assert period > 0
        with self.lock:
            self.period = period
            self.next = self.last + period
            self.cond.notify()

    def cancel(self) -> None:
        """Cancel the periodic operation, and wait until the thread has joined.

        If an operation is currently active, this will wait until it finishes.
        """
        with self.lock:
            self.stop = True
            self.cond.notify()
        self.join()

    def __enter__(self) -> "PeriodicTask":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        self.cancel()

    #######################################################################################
    # Implementation details

    def run(self) -> None:
        """Implementation of the periodic thread."""
        while True:
            with self.lock:
                if self.stop:
                    return

                now = self.clock()
                if now < self.next:
                    if self._expect_run is True:
                        raise AssertionError(
                            f"Unexpected wait: next is {self.next} now is {now}"
                        )
                    self.cond.wait(timeout=self.next - now)
                    continue
                elif self._expect_run is False:
                    raise AssertionError(
                        f"Unexpected not-wait: next is {self.next} now is {now}"
                    )

                self.last = now
                self.next = now + self.period
                self._expect_run = None

            try:
                self.function()
            except BaseException:
                sys.stderr.write(f"Exception in periodic thread {self.name}")
                traceback.print_exc(file=sys.stderr)
                if self.die_on_exception:
                    signal.raise_signal(self.death_signal)

            self.first.set()

    def _test_poke(self, expect_run: bool) -> None:
        """Test helper: Interrupt any pending waits. Used after changing the clock.

        Args:
            expect_run: If true, expect that after this call we'll go back into a wait state.
                If false, expect that we'll pass.
        """
        with self.lock:
            self._expect_run = expect_run
            self.cond.notify()
