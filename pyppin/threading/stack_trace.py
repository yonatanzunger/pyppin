import io
import sys
import threading
import traceback
from collections import defaultdict
from enum import Enum
from types import FrameType, TracebackType
from typing import Dict, List, NamedTuple, Optional

# TODO: Figure out a way to remove "boring" frame lines, like 50 lines in a row inside site packages
# and Python packages.


class TraceLineType(Enum):
    # The "intro" block for a thread
    THREAD_TITLE = 0
    # A part of the stack trace
    TRACE_LINE = 1
    # An exception warning
    EXCEPTION = 2


class TraceLine(NamedTuple):
    # One "line" of the stack trace, including a trailing newline. This may also include internal
    # newlines.
    line: str
    line_type: TraceLineType


class ThreadStack(object):
    def __init__(
        self,
        thread: threading.Thread,
        stack: Optional[traceback.StackSummary],
        exception: Optional[Exception],
    ) -> None:
        """A ThreadStack represents a single thread and its stack info.

        You generally acquire these objects with functions like all_stacks, below.
        """
        self.thread = thread
        self.stack = stack
        self.exception = exception
        self._formatted: Optional[List[TraceLine]] = None
        self._id: Optional[int] = None

    @property
    def is_started(self) -> bool:
        return self.thread.ident is not None

    @property
    def is_daemon(self) -> bool:
        return self.thread.daemon

    @property
    def formatted(self) -> List[TraceLine]:
        """This thread's stack, formatted as a list of TraceLines."""
        if self._formatted is None:
            self._formatted = _format_stack(self)
        return self._formatted

    @property
    def id(self) -> int:
        """Returns an int which is distinct if two threads have meaningfully different stack
        traces.
        """
        if self._id is None:
            self._id = hash(
                tuple(
                    line.line
                    for line in self.formatted
                    if line.line_type in (TraceLineType.TRACE_LINE, TraceLineType.EXCEPTION)
                )
            )
        return self._id


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
    return _SysState().get_all_stacks(limit=limit, daemons=daemons)


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
    stacks: List[ThreadStack], output: Optional[io.TextIOBase] = None, group: bool = True
) -> None:
    """Print a collection of thread stacks.

    Args:
        stacks: The stacks to print.
        output: Where to write them to, defaulting to stderr.
        group: If True, group together threads with identical traces.
    """
    print_trace(format_stacks(stacks, group=group), output=output)


def print_all_stacks(
    output: Optional[io.TextIOBase] = None,
    limit: Optional[int] = None,
    daemons: bool = True,
    group: bool = True,
) -> None:
    """Print the stack traces of all active threads.

    Args:
        output: Where to write the output; defaults to stderr.
        limit: As the argument to all_stacks.
        daemons: Whether to include daemon threads.
        group: If True, group together threads with identical traces.
    """
    print_stacks(all_stacks(limit=limit, daemons=daemons), output=output, group=group)


#################################################################################################
# Implementation details begin here


# Logic for getting stacks
class _SysState(object):
    def __init__(self) -> None:
        """This is a class that manages actually fetching stack summaries out of Python. It holds a
        bunch of frame and traceback pointers, which means you should only keep this object alive in
        a _very_ narrow scope, or you will (a) get bogus results and (b) basically shut down GC. So
        don't do that. In fact, you shouldn't be invoking this class except via the functions above
        that use it; there's a reason this thing has an underscore in its name.
        """
        self.frames: Dict[int, FrameType] = sys._current_frames()
        # Dictionary from thread ID to the exception in that thread, if that thread has an
        # exception.
        self.exceptions: Dict[int, BaseException] = {}

        # The nice, Python 3.10+ way to do this
        if hasattr(sys, '_current_exceptions'):
            self.exceptions = sys._current_exceptions()
        else:
            # Old Python versions lack this, so we're going to build up the dictionary the hard way.
            exc_info = sys.exc_info()
            if exc_info[0] is not None:
                assert isinstance(exc_info[1], BaseException)
                assert isinstance(exc_info[2], TracebackType)

                # Figure out which thread contains the exception traceback. Here's the frame where
                # the exception is going on:
                # XXX THIS LOGIC IS WRONG -- the thing in self.frames is likely to be in the
                # exception _handler_, so of course its current frame won't match that of the
                # exception. How else do we figure out the thread ID in which the exception is
                # happening??
                # XXX Possibility: We may need to only use self.exceptions in 3.10, and for earlier
                # versions, store the exception and its stack frame separately, and print them out
                # as though they're a separate thread, without any thread title info! That'll mean
                # making the Thread object in a ThreadStack optional.
                exc_frame = exc_info[2].tb_frame
                for ident, frame in self.frames.items():
                    if frame == exc_frame:
                        self.exceptions[ident] = exc_info[1]
                        break
                else:
                    # There's an exception, but we can't find the thread it's in??
                    # TODO print some kind of error here.
                    sys.stderr.write(
                        f'Strange: There is an active exception ({exc_info[1]}), but its frame '
                        f'is nowhere to be found.\n'
                    )

    def get_stack(self, thread: threading.Thread, limit: Optional[int]) -> ThreadStack:
        return ThreadStack(
            thread=thread,
            stack=self._stack_summary(thread, limit=limit),
            exception=self._exception(thread),
        )

    def get_all_stacks(self, limit: Optional[int], daemons: bool) -> List[ThreadStack]:
        result: Dict[int, ThreadStack] = {}
        dummy_id = -1
        for thread in threading.enumerate():
            if daemons or not thread.daemon:
                thread_id: int
                if thread.ident is not None:
                    thread_id = thread.ident
                else:
                    thread_id = dummy_id
                    dummy_id -= 1
                result[thread_id] = self.get_stack(thread, limit=limit)

        # If there's any active exceptions, load those as well.
        for thread_id, exception in self.exceptions.items():
            # *Replace* the current stack trace of this exception with the exception trace.
            old_stack = result.get(thread_id, None)
            if old_stack is None:
                # TODO print some kind of error here
                continue
            result[thread_id] = old_stack._replace(
                stack=self._exception_stack_summary(exception), exception=exception
            )

        return list(result.values())

    def _stack_summary(
        self, thread: threading.Thread, limit: Optional[int]
    ) -> Optional[traceback.StackSummary]:
        if thread.ident is None or thread.ident not in self.frames:
            # Unstarted thread or missing stack.
            return None
        return traceback.extract_stack(self.frames[thread.ident], limit=limit)

    def _exception_stack_summary(
        self, exception: BaseException, limit: Optional[int]
    ) -> traceback.StackSummary:
        return traceback.extract_stack(exception.__traceback__.tb_frame, limit=limit)

    def _exception(self, thread: threading.Thread) -> Optional[BaseException]:
        if thread.ident is None:
            return None
        else:
            return self.exceptions.get(thread.ident, None)


def _get_state() -> _SysState:
    if hasattr(sys, '_current_exceptions'):
        return _SysState(frames=sys._current_frames(), exceptions=sys._current_exceptions())
    else:
        exc_info = sys.exc_info()
        return _SysState(frames=sys._current_frames(), exception=exc_info[1], exc_tb=exc_info[2])


# Logic for turning stacks into lists of TraceLines


def _thread_str(thread: threading.Thread) -> str:
    d = 'daemon; ' if thread.daemon else ''
    if thread.ident is not None:
        return f'"{thread.name}" ({d}{thread.ident}, TID {thread.native_id})'
    else:
        return f'"{thread.name}" ({d}not started)'


def _format_stack(stack: ThreadStack, title: Optional[str] = None) -> List[TraceLine]:
    """Format just this thread into a list of trace lines."""
    title = title or 'Thread ' + _thread_str(stack.thread)

    result: List[TraceLine] = []
    result.append(TraceLine(title + '\n', TraceLineType.THREAD_TITLE))

    # Early-exit for unstarted threads
    if not stack.is_started:
        return result

    if stack.stack is None:
        result.append(TraceLine('<No stack found>\n', TraceLineType.TRACE_LINE))
    else:
        for line in stack.stack.format():
            result.append(TraceLine(line, TraceLineType.TRACE_LINE))

    if stack.exception is not None:
        result.append(TraceLine(f'Exception: {stack.exception}\n', TraceLineType.EXCEPTION))

    return result


MAX_THREADS_NAMED = 3


def _format_stack_group(stacks: List[ThreadStack]) -> List[TraceLine]:
    """Format a group of threads with identical stacks."""
    assert len(stacks)
    title: Optional[str] = None
    if len(stacks) > 1:
        first_names = ", ".join(_thread_str(stack.thread) for stack in stacks[:MAX_THREADS_NAMED])
        title = f'{len(stacks)} Threads: {first_names}'
        if len(stacks) > MAX_THREADS_NAMED:
            title += ' and others'

    return _format_stack(stacks[0], title=title)


ThreadGroup = Dict[int, List[ThreadStack]]


def _append_group(result: List[TraceLine], group: ThreadGroup) -> None:
    for stacks in group.values():
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

        group[stack.id].append(stack)

    # Now let's format the groups. We'll put the special groups at the end.
    result: List[TraceLine] = []
    _append_group(result, unstarted_threads)
    _append_group(result, started_daemons)
    _append_group(result, started_non_daemons)
    _append_group(result, failing)
    return result


def _format_without_group(stacks: List[ThreadStack]) -> List[TraceLine]:
    result: List[TraceLine] = []
    for stack in stacks:
        result.extend(_format_stack(stack))
    return result


# Logic for printing things out


class _LineWrap(NamedTuple):
    before: str = ""
    after: str = ""

    def wrap(self, line: str) -> str:
        return self.before + line + self.after

    @classmethod
    def color(cls, *colors: int) -> '_LineWrap':
        # Pick a VT100 color
        colors = ";".join(str(x) for x in colors)
        return cls(before=f'\x1b[{colors}m', after='\x1b[0m')


class _LineWraps(object):
    def __init__(self, data: Dict[TraceLineType, _LineWrap]) -> None:
        self.data = data

    def wrap(self, line: TraceLine) -> str:
        return self.data[line.line_type].wrap(line.line)


NON_TTY_WRAPS = _LineWraps(
    {
        TraceLineType.THREAD_TITLE: _LineWrap(),
        TraceLineType.TRACE_LINE: _LineWrap(),
        TraceLineType.EXCEPTION: _LineWrap(),
    }
)

TTY_WRAPS = _LineWraps(
    {
        TraceLineType.THREAD_TITLE: _LineWrap(1),  # Bright
        TraceLineType.TRACE_LINE: _LineWrap(),
        TraceLineType.EXCEPTION: _LineWrap.color(31, 1),  # Red and bright
    }
)


def _write(file: io.TextIOBase, trace: List[TraceLine]) -> None:
    """Write a trace, nicely formatted, to a file."""
    wraps = TTY_WRAPS if file.isatty() else NON_TTY_WRAPS
    for entry in trace:
        file.write(wraps.wrap(entry))
