import io
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from types import TracebackType
from typing import Dict, Optional, Type, Union

from pyppin.text.formatter import Formatter


class PrintCounter(object):
    def __init__(
        self,
        print_every_n: Optional[Union[int, float]] = 10000,
        print_every_time: Optional[timedelta] = timedelta(seconds=30),
        format: str = "Count: {count:si} after {time:td}",
        final_format: Optional[str] = "Final: {count} after {time:td}",
        start: Optional[datetime] = None,
        stream: Optional[io.TextIOBase] = None,
    ) -> None:
        """A PrintCounter is a context manager that prints regular updates of progress.

        It prints the updates on separate lines, without any VT100 formatting or the like, so it's
        useful in situations where you're writing log files as well as on the console.

        Its use is simple:

        with PrintCounter() as counter:
            ... do some big loop and occasionally call
            counter.inc()

        Every N calls to counter.inc(), or whenever at least Δ time has passed since the last call
        to inc(), it will print out an update statement. The use of both count and time lets you
        edeasily monitor both fast and slow operations and always get useful feedback.

        You can also have "custom counters" by adding keyword arguments to inc(). These counters are
        available in your format string as well to print out, but (unlike the primary counter) they
        will *not* trigger printing.

        Args:
            print_every_n: If not None, print whenever it's been at least N counts since the last
                print happened.
            print_every_time: If not None, print whenever it's been at least X time since the last
                print happened.
            format: The string to print out. This is a standard Python format string, which receives
                the arguments:
                    count: int or float, the current count
                    time: timedelta, the total elapsed time
                    **custom_counts: Any custom counts you created, int or float.
            final_format: If given, the format to be used for the final print string. If None, equal
                to 'format'. Note that the default deliberately uses the raw format for count, not
                the SI one, so you get an exact final count!
            start: The zero time for measurement; the default is now.
            stream: Where to print the result to, or None to print to stdout.
        """
        self.print_every_n = print_every_n
        self.print_every_time = print_every_time
        self.format = format
        self.final_format = final_format if final_format is not None else format
        self.start = start if start is not None else datetime.now()
        self.formatter = Formatter()
        self.stream = stream or sys.stdout

        self.count: Union[int, float] = 0
        self.custom_counts: Dict[str, Union[int, float]] = defaultdict(int)
        self.next_print_time = (
            self.start + self.print_every_time if self.print_every_time else None
        )
        self.next_print_count = self.print_every_n

    def inc(self, count: Union[int, float] = 1, **custom: Union[int, float]) -> None:
        """Increment the counter.

        Args:
            count: The amount by which to increment the primary counter.
            **custom: Any number of custom counters you would also like to increment.
        """
        self.count += count
        for key, value in custom.items():
            self.custom_counts[key] += value
        self._maybe_print()

    def __enter__(self) -> "PrintCounter":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self._print(datetime.now(), is_final=True)

    def _maybe_print(self) -> None:
        if self.next_print_count is not None and self.count >= self.next_print_count:
            self._print(datetime.now())
        if self.next_print_time is not None:
            now = datetime.now()
            if now >= self.next_print_time:
                self._print(now)

    def _print(self, now: datetime, is_final: bool = False) -> None:
        format_string = self.final_format if is_final else self.format
        self.stream.write(
            self.formatter.format(
                format_string,
                count=self.count,
                time=(now - self.start),
                **self.custom_counts
            )
        )
        self.stream.write("\n")
        self.next_print_time = (
            now + self.print_every_time if self.print_every_time else None
        )
        self.next_print_count = (
            self.count + self.print_every_n if self.print_every_n else None
        )
