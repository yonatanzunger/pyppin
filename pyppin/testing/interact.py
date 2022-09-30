"""A function to open an interactive debugging REPL anywhere in your code."""
import code
import sys
from typing import Callable, Iterable, Optional


def interact(
    banner: Optional[str] = None,
    _test_commands: Optional[Iterable[str]] = None,
) -> None:
    """Open an interactive REPL at any given point in your code.

    This REPL will be able to see, but not modify, any local and global variables visible from the
    point at which you invoke it. (If you *do* modify them, these modifications will be thrown out
    when the REPL exits.) That means that it gives you a lot of the flexibility and power of
    a debugger without the overhead of running your entire program in a debugging environment.

    For example, your code might compute some value in a complicated way, and then use it. Rather
    than using printf debugging, you can use interactive debugging::

        def someFunction(...):
            # ... Compute foo
            interact()  # Instead of print(f"Foo: {foo}")
            # ... Use foo

    When the code reaches interact(), it will stop and pop open a Python shell, from which you
    can simply examine the value of foo (by typing 'foo').

    If you exit the shell with a ^D, your program will resume executing. If you exit the shell by
    calling quit() or exit(), it will abort the entire program (by raising SystemExit).

    Args:
      banner: If given, a banner to show at the start of the interactive environment.

      _test_commands: UNITTESTING ARGUMENT ONLY! Simulates user input as a list of commands.

    Helpful tip: If you're running a test under tox and are getting an error that stdin can't be
    read, but want to interact() to debug something from inside a unittest, change your tox.ini
    so that the test command is 'pytest -s'. That's not what you usually want -- it disables stdout
    capture as well -- but it will let you interactively probe your tests!

    FUTURE NOTE: A read-write interacting environment may become possible in future versions of
    Python; see PEP 558, which would be required in order to implement this.
    """

    # Convert _test_commands into an (optional) function of the right signature to serve as the
    # command source for an interactive shell.
    _test_input: Optional[Callable[[str], str]] = None
    if _test_commands is not None:
        command = iter(_test_commands)

        def _test_input(prompt: str = "") -> str:
            nonlocal command
            try:
                return next(command)
            except StopIteration:
                raise EOFError()

    # Now, grab the local and global variables from the stack layer from which we were invoked.
    stack = sys._getframe(1)
    try:
        # Annoying bug we need to work around: The `code` library doesn't propagate globals into its
        # child frame at all, which would lead to unexpected surprises like "you can't see global
        # variables." So we copy the globals into the nested frame of variables that we'll propagate
        # down, _along with_ the locals.
        nestedlocals = dict(stack.f_globals)
        nestedlocals.update(stack.f_locals)

        # Invoke the REPL. If this raises SystemExit, let it through.
        code.interact(
            banner=banner,
            readfunc=_test_input,
            local=nestedlocals,
        )

    finally:
        # Keeping references to stack frames around can do unpleasant things to the GC. For more
        # details on why we do this explicitly, see
        # https://docs.python.org/3/library/inspect.html#the-interpreter-stack
        del nestedlocals
        del stack
