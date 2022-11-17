"""The actual meat of stack tracing.

This file contains the "advanced" API which most users won't need, as well as the implementation
details; it lets you do things like examine and programmatically manipulate the threads of all
stacks. Most users can stick to :doc:`pyppin.threading.stack_trace` instead.

Warning
=======
The non-public methods in this library are non-public for a reason; they are subtle and quick to
anger. Do not mess with them unless you understand Python's GC system quite well.
"""

import io
import sys
import threading
import traceback
from abc import ABC, abstractmethod
from collections import defaultdict
from enum import Enum
from types import FrameType
from typing import Dict, Iterable, Iterator, List, NamedTuple, Optional, TextIO, Union

#################################################################################################
# More advanced API's, if you want to muck with the stack traces yourself


class TraceLineType(Enum):
    """The different kinds of line in a trace that may require different visual representation."""

    THREAD_TITLE = 0
    """The "intro" block for a thread"""

    TRACE_LINE = 1
    """A part of the stack trace"""

    EXCEPTION = 2
    """An exception warning"""


class TraceLine(NamedTuple):
    """One logical "line" of the stack trace, including a trailing newline.

    It's only a logical line; this may also include internal newlines.
    """

    line: str
    """The actual text of the line."""

    line_type: TraceLineType
    """How the line should be rendered."""

    def prepend(self, data: str) -> "TraceLine":
        """Create a new ``TraceLine`` by prepending text to this one."""
        return self._replace(line=data + self.line)

    @classmethod
    def as_trace(
        cls,
        lines: Iterable[str],
        line_type: TraceLineType = TraceLineType.TRACE_LINE,
        prefix: str = "",
    ) -> Iterator["TraceLine"]:
        """Convert a sequence of lines of text to a sequence of ``TraceLines``."""
        for line in lines:
            yield TraceLine(prefix + line, line_type)

    @classmethod
    def blank(cls) -> "TraceLine":
        """A blank ``TraceLine``."""
        return TraceLine("\n", TraceLineType.TRACE_LINE)


class ThreadStack(object):
    """A ThreadStack represents a single thread and its stack info.

    You generally acquire these objects with functions like all_stacks, below.

    NB that self.exception is going to be a TracebackException object, *not* the original
    exception, in order to avoid all sorts of exciting reference counting cycles and other
    things that can make your life unpleasant. Net is that it's safe to keep one of these
    objects around, you don't need to do magical "dear-gods-delete-this-quickly" magic like with
    frame objects.
    """

    def __init__(
        self,
        thread: Optional[threading.Thread],
        stack: Optional[traceback.StackSummary],
        exception: Optional[BaseException],
    ) -> None:
        # These are public variables, and you can look at them!
        self.thread = thread
        self.stack = stack
        self.exception = (
            traceback.TracebackException.from_exception(exception)
            if exception
            else None
        )

        self._formatted: Optional[List[TraceLine]] = None
        self._cluster_id: Optional[int] = None

    @property
    def thread_unknown(self) -> bool:
        """Returns true if we don't actually know what thread this is."""
        return self.thread is not None

    @property
    def is_started(self) -> bool:
        """Returns true if the thread is active."""
        return self.thread is None or self.thread_id is not None

    @property
    def thread_id(self) -> Optional[int]:
        """The Python ID of this thread, if it's started."""
        return self.thread.ident if self.thread is not None else None

    @property
    def native_thread_id(self) -> Optional[int]:
        """The native thread ID of this thread, if it's started."""
        return self.thread.native_id if self.thread is not None else None

    @property
    def is_daemon(self) -> bool:
        """Whether this is a daemon thread."""
        return self.thread is not None and self.thread.daemon

    @property
    def formatted(self) -> List[TraceLine]:
        """This thread's stack, formatted as a list of TraceLines."""
        if self._formatted is None:
            self._formatted = _format_stack(self)
        return self._formatted

    @property
    def cluster_id(self) -> int:
        """A "similarity identifier" for this thread's stack trace.

        If two threads have the same cluster ID, then their stack traces are effectively identical
        and (if grouping is turned on) should be merged in rendering.

        This is especially useful if you have a bunch of "listener" or "worker" threads in your
        program which may be doing the same thing; it greatly simplifies the stack trace without
        losing data.
        """
        if self._cluster_id is None:
            self._cluster_id = hash(
                tuple(
                    line.line
                    for line in self.formatted
                    if line.line_type
                    in (TraceLineType.TRACE_LINE, TraceLineType.EXCEPTION)
                )
            )
        return self._cluster_id

    @property
    def name(self) -> str:
        """A name for this thread, suitable for use as a title in a trace."""

        if self.thread is None:
            if self.exception is None:
                return "Unknown thread"
            else:
                return "Exception thread (can only be tied to an actual thread ID in Python 3.10+)"

        d = "daemon; " if self.thread.daemon else ""
        if self.thread.ident is not None:
            return f'Thread "{self.thread.name}" ({d}{self.thread.ident}, TID {self.thread.native_id})'
        else:
            return f'Thread "{self.thread.name}" ({d}not started)'


def all_stacks(limit: Optional[int] = None, daemons: bool = True) -> List[ThreadStack]:
    """Return the stack summaries for all active threads.

    Args:
        limit: If given, this is the maximum number of stack trace entries to return for each
            thread. (This is the same meaning as the argument of the same name used in the traceback
            module)
        daemons: If True, include daemon threads.

    Returns:
        All the active threads, in no particular order.
    """
    return _FrameState.all_stacks(limit=limit, daemons=daemons)


def format_stacks(stacks: List[ThreadStack], group: bool = True) -> List[TraceLine]:
    """Format a list of stacks neatly for printing.

    Args:
        stacks: The stacks to format.
        group: If True, group together threads with identical traces.
    """
    return _format_and_group(stacks) if group else _format_without_group(stacks)


def print_trace(lines: List[TraceLine], output: Optional[io.TextIOBase] = None) -> None:
    """Print a list of trace lines.

    Args:
        lines: The lines to print.
        output: Where to write them to, defaulting to stderr.
    """
    _write(output or sys.stderr, lines)


def print_stacks(
    stacks: List[ThreadStack],
    output: Optional[io.TextIOBase] = None,
    group: bool = True,
) -> None:
    """Print a collection of thread stacks.

    Args:
        stacks: The stacks to print.
        output: Where to write them to, defaulting to stderr.
        group: If True, group together threads with identical traces.
    """
    print_trace(format_stacks(stacks, group=group), output=output)


#################################################################################################
# Implementation details begin here


class _FrameState(ABC):
    """This is a class that manages actually fetching stack summaries out of Python. It holds a
    bunch of frame and traceback pointers, which means you should only keep this object alive in
    a _very_ narrow scope, or you will (a) get bogus results and (b) basically shut down GC. So
    don't do that. In fact, you shouldn't be invoking this class except via the functions above
    that use it; there's a reason this thing has an underscore in its name.

    It comes in two variants, because there's a "good" way to do this that produces nice traces, but
    requires Python 3.10+, and a "lousy" way that works on earlier versions.
    """

    @abstractmethod
    def get_stack(self, thread: threading.Thread, limit: Optional[int]) -> ThreadStack:
        """Get a ThreadStack for a single thread."""
        ...

    @abstractmethod
    def get_all_stacks(self, limit: Optional[int], daemons: bool) -> List[ThreadStack]:
        """Get all the ThreadStacks."""
        ...

    @staticmethod
    def all_stacks(limit: Optional[int], daemons: bool) -> List[ThreadStack]:
        """This is safer than calling make() directly, since it makes sure to avoid refcounting
        loops. Read https://docs.python.org/3/library/inspect.html#the-interpreter-stack if you're
        wondering what this is or why. I'm not bothering with a "safe easy-to-use" API for this
        because this is an internal class for a _reason._
        """
        try:
            state = _FrameState.make()
            return state.get_all_stacks(limit=limit, daemons=daemons)
        finally:
            del state

    @staticmethod
    def make() -> "_FrameState":
        return (
            _FrameState310() if hasattr(sys, "_current_exceptions") else _FrameState39()
        )


class _FrameState39(_FrameState):
    """Version that works on Python 3.9 and earlier"""

    def __init__(self) -> None:
        self.frames: Dict[int, FrameType] = sys._current_frames()
        # In earlier versions of Python, there's no way to find the thread from an exception, so
        # instead, # if there is an active exception, we store its exc_info here, and print it
        # out like a fake "extra" thread -- because there's no way to know which thread it came
        # from! Sigh.
        self.exception: Optional[BaseException] = sys.exc_info()[1]

    def get_stack(self, thread: threading.Thread, limit: Optional[int]) -> ThreadStack:
        # Alas, the exception here is always going to be None, because if there is an exception, we
        # have no way to tie it to the thread. :(
        frame: Optional[FrameType] = (
            self.frames[thread.ident]
            if thread.ident is not None and thread.ident in self.frames
            else None
        )

        return ThreadStack(
            thread=thread,
            stack=traceback.extract_stack(frame, limit=limit)
            if frame is not None
            else None,
            exception=None,
        )

    def get_extra_stack(self, limit: Optional[int]) -> Optional[ThreadStack]:
        """If there's an active exception, and we're in pre-3.10 land, create a fake "extra"
        stack entry for the exception.
        """
        return (
            ThreadStack(
                thread=None,
                stack=None,
                exception=self.exception,
            )
            if self.exception is not None
            else None
        )

    def get_all_stacks(self, limit: Optional[int], daemons: bool) -> List[ThreadStack]:
        result = [
            self.get_stack(thread, limit=limit)
            for thread in threading.enumerate()
            if daemons or not thread.daemon
        ]
        extra = self.get_extra_stack(limit)
        if extra is not None:
            result.append(extra)

        return result


class _FrameState310(_FrameState):
    """Version that works on Python 3.10+, and gets exception handling right."""

    def __init__(self) -> None:
        self.frames: Dict[int, FrameType] = sys._current_frames()
        self.exceptions: Dict[int, BaseException] = {
            thread_id: exc_info[1]
            for thread_id, exc_info in sys._current_exceptions().items()  # type: ignore
        }

    def get_stack(self, thread: threading.Thread, limit: Optional[int]) -> ThreadStack:
        exception = (
            self.exceptions.get(thread.ident, None)
            if thread.ident is not None
            else None
        )
        frame: Optional[FrameType]
        if exception is not None:
            # Use the exception's stack frame, not the one where we're executing the stack trace
            # printer!
            frame = (
                exception.__traceback__.tb_frame if exception.__traceback__ else None
            )
        elif thread.ident is not None and thread.ident in self.frames:
            frame = self.frames[thread.ident]
        else:
            frame = None

        return ThreadStack(
            thread=thread,
            stack=traceback.extract_stack(frame, limit=limit)
            if frame is not None
            else None,
            exception=exception,
        )

    def get_all_stacks(self, limit: Optional[int], daemons: bool) -> List[ThreadStack]:
        return [
            self.get_stack(thread, limit=limit)
            for thread in threading.enumerate()
            if daemons or not thread.daemon
        ]


# Logic for turning stacks into lists of TraceLines


def _format_stack(stack: ThreadStack, title: Optional[str] = None) -> List[TraceLine]:
    """Format just this thread into a list of trace lines."""
    title = title or stack.name

    result: List[TraceLine] = []
    result.append(TraceLine(title + "\n", TraceLineType.THREAD_TITLE))

    # Early-exit for unstarted threads
    if not stack.is_started:
        return result

    if stack.stack:
        result.extend(TraceLine.as_trace(stack.stack.format()))
    else:
        result.append(TraceLine("<No stack found>\n", TraceLineType.TRACE_LINE))

    if stack.exception:
        result.append(
            TraceLine(
                f"Exception: {stack.exception.exc_type.__name__}: {stack.exception}\n",
                TraceLineType.EXCEPTION,
            )
        )
        result.extend(TraceLine.as_trace(stack.exception.format()))

    return result


MAX_THREADS_NAMED = 3


def _format_stack_group(stacks: List[ThreadStack]) -> List[TraceLine]:
    """Format a group of threads with identical stacks."""
    assert len(stacks)
    title: Optional[str] = None
    if len(stacks) > 1:
        first_names = ", ".join(stack.name for stack in stacks[:MAX_THREADS_NAMED])
        title = f"{len(stacks)} Threads: {first_names}"
        if len(stacks) > MAX_THREADS_NAMED:
            title += " and others"

    return _format_stack(stacks[0], title=title)


ThreadGroup = Dict[int, List[ThreadStack]]


def _append_group(
    result: List[TraceLine], group: ThreadGroup, is_first: bool = False
) -> None:
    for index, stacks in enumerate(group.values()):
        if index or not is_first:
            result.append(TraceLine.blank())
        result.extend(_format_stack_group(stacks))


def _format_and_group(stacks: List[ThreadStack]) -> List[TraceLine]:
    # First, let's group the stacks.
    unstarted_threads: ThreadGroup = defaultdict(list)
    started_daemons: ThreadGroup = defaultdict(list)
    started_non_daemons: ThreadGroup = defaultdict(list)
    failing: ThreadGroup = defaultdict(list)

    group: ThreadGroup
    for stack in stacks:
        if not stack.is_started:
            group = unstarted_threads
        elif stack.exception is not None:
            group = failing
        elif stack.is_daemon:
            group = started_daemons
        else:
            group = started_non_daemons

        group[stack.cluster_id].append(stack)

    # Now let's format the groups. We'll put the special groups at the end.
    result: List[TraceLine] = []
    _append_group(result, unstarted_threads, is_first=True)
    _append_group(result, started_daemons)
    _append_group(result, started_non_daemons)
    _append_group(result, failing)
    return result


def _format_without_group(stacks: List[ThreadStack]) -> List[TraceLine]:
    result: List[TraceLine] = []
    for index, stack in enumerate(stacks):
        if index:
            result.append(TraceLine.blank())
        result.extend(_format_stack(stack))
    return result


# Logic for printing things out


class _LineWrap(NamedTuple):
    before: str = ""
    after: str = ""

    def wrap(self, line: str) -> str:
        return self.before + line + self.after

    @classmethod
    def color(cls, *colors: int) -> "_LineWrap":
        # Pick a VT100 color
        codes = ";".join(str(x) for x in colors)
        return cls(before=f"\x1b[{codes}m", after="\x1b[0m")


class _LineWraps(object):
    def __init__(self, data: Dict[TraceLineType, _LineWrap]) -> None:
        self.data = data

    def wrap(self, line: TraceLine) -> str:
        return self.data[line.line_type].wrap(line.line)


_NON_TTY_WRAPS = _LineWraps(
    {
        TraceLineType.THREAD_TITLE: _LineWrap(),
        TraceLineType.TRACE_LINE: _LineWrap(),
        TraceLineType.EXCEPTION: _LineWrap(),
    }
)

_TTY_WRAPS = _LineWraps(
    {
        TraceLineType.THREAD_TITLE: _LineWrap.color(1),  # Bright
        TraceLineType.TRACE_LINE: _LineWrap(),
        TraceLineType.EXCEPTION: _LineWrap.color(31, 1),  # Red and bright
    }
)


def _write(file: Union[TextIO, io.TextIOBase], trace: List[TraceLine]) -> None:
    """Write a trace, nicely formatted, to a file."""
    wraps = _TTY_WRAPS if file.isatty() else _NON_TTY_WRAPS
    for entry in trace:
        file.write(wraps.wrap(entry))
