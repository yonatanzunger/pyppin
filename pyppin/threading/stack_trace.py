"""A library to dump stack traces from *all* threads, not just the current one.

This library contains the "simple" API, which is all 99% of users will ever need. Its main functions
are ``print_all_stacks()``, which does what it says on the tin, and
``print_all_stacks_on_failure()``, which you can call during program initialization to make
printing all stack traces be the default behavior whenever there's an uncaught exception.

Another useful API is in :doc:`pyppin.testing.trace_on_failure`, which contains a decorator that
you can attach to functions, methods, or entire unittest cases to make them print all stacks
whenever there's an uncaught exception. (Note that if you do that, "an uncaught exception" includes
``KeyboardInterrupt``, so you can ctrl-C out of a deadlock and see what's going on!)

If you want a more low-level API that lets you directly grab these stacks and manipulate them
programmatically, that's found in :doc:`pyppin.threading.stack_trace_internals`.

Note
====
If you're printing out a stack trace when there's an exception being handled, in Python 3.9 or
earlier the exception will be printed out *after* the stack trace, because there's no way to tie an
exception to the thread that raised it. In Python 3.10 or later, this is fixed, and exceptions are
shown with the offending threads.
"""

import io
import sys
from types import TracebackType
from typing import Optional, Type

from pyppin.threading.stack_trace_internals import all_stacks, print_stacks

# NB: This library is unittested in tests/testing/trace_on_failure_test.py, which also tests the
# handy unittest wrappers for it.


def print_all_stacks(
    output: Optional[io.TextIOBase] = None,
    limit: Optional[int] = None,
    daemons: bool = True,
    group: bool = True,
) -> None:
    """Print the stack traces of all active threads.

    Args:
        output: Where to write the output; defaults to stderr.
        limit: If set, the maximum number of stack trace entries to return per thread. (This has the
            same meaning as the argument of the same name used in the `traceback
            <https://docs.python.org/3/library/traceback.html>`_ module)
        daemons: Whether to include daemon threads.
        group: If True, group together threads with identical traces.
    """
    print_stacks(all_stacks(limit=limit, daemons=daemons), output=output, group=group)


def print_all_stacks_on_failure() -> None:
    """Change the handling of uncaught exceptions to print *all* stacks.

    This is usually something you call from main() or otherwise during program initialization,
    if you want any uncaught exceptions to dump all the thread stacks.

    If you want to apply this logic just to a single function or method call, check out
    :doc:`pyppin.testing.trace_on_failure` instead.
    """

    def _excepthook(
        exc_type: Type[BaseException],
        value: BaseException,
        traceback: Optional[TracebackType],
    ) -> None:
        print_all_stacks()

    sys.excepthook = _excepthook

    if hasattr(sys, "unraisablehook"):

        def _unraisablehook(exc: sys.UnraisableHookArgs) -> None:
            print_all_stacks()

        sys.unraisablehook = _unraisablehook
