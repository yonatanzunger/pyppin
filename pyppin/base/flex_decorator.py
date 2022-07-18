import inspect
from typing import Callable


def flex_decorator(decorator: Callable) -> Callable:
    """flex_decorator is a way to simplify writing Python decorators and improve their syntax.

    Usually, if you want to write a decorator without arguments, you have to write one kind of
    function, and the resulting syntax is @foo def bar(), but if you want to write a decorator that
    takes arguments, you have to write a completely different function, and the resulting syntax is
    @foo() def bar. While there are good reasons for this to be the implementation, it's ugly and
    requires remembering too many things for both the writer and user of decorators.

    Instead, @flex_decorator simplifies all of this. You simply need to write

    @flex_decorator
    def my_decorator(target, *, arg, arg, ...):
       ... return the decorated "target"

    You only write one function: it takes exactly one positional argument (the thing to be
    decorated), and arbitrarily many keyword arguments. You can then use the resulting decorator in
    two ways:

    @my_decorator(arg=foo, arg=bar)
    def decorated_thing(...):

    or, if all of the arguments have default values, you can write

    @my_decorator
    def decorated_thing(...):

    This is identical to @my_decorator(), so users no longer need to remember which one to use.
    """
    # First, make sure the thing we're decorating has a decoratable signature.
    signature = inspect.getfullargspec(decorator)
    if signature.varargs or len(signature.args) != 1:
        raise TypeError(
            '@flex_decorator must decorate a function that takes exactly one positional '
            'argument, the object to be decorated. All other arguments must be keyword-only.'
        )

    defaults = signature.kwonlydefaults or {}
    kw_args_without_defaults = sorted(key for key in signature.kwonlyargs if key not in defaults)

    # We'll generate a better decorator out of decorator, and return that. This means that
    # @flex_decorator def my_decorator(...) causes the symbol my_decorator to be defined as the
    # function better_decorator. The resulting object can be used with two syntaxes.
    #
    # SYNTAX 1:
    #   @my_decorator
    #   def foo(...)
    #       ==> This is equivalent to
    #         def _foo(...)
    #         foo = better_decorator(_foo)
    #       i.e., better_decorator is called with a single argument, the function to be decorated,
    #       and should return the decorated version of the function, i.e. decorator(_foo). Clearly,
    #       this syntax only works if there are no KW arguments to decorator that lack defaults.
    #
    # SYNTAX 2:
    #   @my_decorator(arg1=X, arg2=Y, ...)
    #   def foo(...)
    #       ==> This is equivalent to
    #         def _foo(...)
    #         _decorator = better_decorator(arg1=X, arg2=Y, ...)
    #         foo = _decorator(_foo)
    #       i.e., better_decorator is called with only keyword arguments, and should return a zero-
    #       argument decorator which maps _foo onto decorator(_foo, arg1=X, arg2=Y, ...).
    def better_decorator(*args, **kwargs) -> Callable:
        if len(args) == 1 and not kwargs:
            # Call using the first syntax. This call mode only works if all the kwargs in decorator
            # have defaults!
            if kw_args_without_defaults:
                raise TypeError(
                    f'The decorator {decorator.__name__} does not have default values specified '
                    f'for the argument(s) {", ".join(kw_args_without_defaults)}. You must '
                    f'therefore use it with the syntax @{decorator.__name__}(arg=foo, ...) def '
                    f'thing_to_be_decorated(...).'
                )
            # We're acting like a zero-argument decorator; simply apply decorator to this!
            return decorator(args[0])

        elif not args:
            # Call using the second syntax. We need to return a zero-argument decorator.
            return lambda target: decorator(target, **kwargs)

        else:
            raise TypeError(f'The decorator {decorator.__name__} must be applied to a callable.')

    return better_decorator
