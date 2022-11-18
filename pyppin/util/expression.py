"""Safe evaluation of Python expressions."""

import ast
import builtins
import sys
from typing import (
    Any,
    Callable,
    Dict,
    List,
    NamedTuple,
    NoReturn,
    Optional,
    Set,
    Tuple,
    Type,
    Union,
)


class Expression(object):
    """Expression implements "safe" evaluation of user-entered Python expressions.

    This is safe in that it tries to ensure that the given expression cannot mutate the state of
    the system (e.g. modifying attributes), execute I/O, or change the broader control flow.
    However, it is not perfectly safe: Sufficiently complex expressions can crash the entire
    interpreter! See compile() for details. Length-limiting the input may help.

    Args:
        expression: A Python expression to be turned into this object.
        functions: A list of functions which may be used in expressions. By default, only the
            "safe" builtin functions (see SAFE_BUILTINS, below) are permitted; any others
            must be explicitly specified.
        allow_attribute_functions: By default, while all attributes of variables passed in to
            the expression may be referenced, if the variable contains a function (e.g.,
            x.foo()) then that function may *not* be called. If this is set to true, such
            functions are permitted. This default makes it safe to pass objects which have
            potentially dangerous methods for their data alone. Note that variable *properties*
            are always accessible.
        variables: If given, a list of variable names which may be referenced by the expression.
            In this case, any reference to variables not in this list will raise a SyntaxError
            at construction time. If not given, all variable names are permitted, and the actual
            set of variables used can be checked with the ``variables`` property of this object.

    Raises:
        SyntaxError: If the expression cannot be parsed, or if the expression attempted to
            do something forbidden, like reference an unknown variable.
        ValueError: If the expression string contains NUL bytes for some reason.
    """

    def __init__(
        self,
        expression: str,
        *,
        functions: List[Callable] = [],
        allow_attribute_functions: bool = False,
        variables: Optional[List[str]] = None,
    ) -> None:
        self._fns: Dict[str, Callable] = _dict_sum(
            SAFE_BUILTINS, {fn.__name__: fn for fn in functions}
        )

        self._ast = ast.parse(expression, mode="eval")
        context = _ValidationContext(
            expression,
            set(variables) if variables is not None else None,
            self._fns,
            allow_attribute_functions,
        )
        context.validate(self._ast)
        self._fn = compile(self._ast, filename="<expression>", mode="eval")
        assert self._fn.co_argcount == 0

    def __call__(self, **kwargs: Any) -> Any:
        """Evaluate the expression, giving it access to any indicated variables.

        Args:
            **kwargs: All the variables which are to be passed to the expression. Note that if any
                member of self.free_variables is not given here, you are very likely to get a
                NameError. You may also replace functions by passing values for them here!

        Returns: The evaluated value of the expression.

        Raises:
            Any exception raised by the expression itself.
            NameError: If some variable referenced by the expression was not given in variables.
        """
        return eval(self._fn, {}, _dict_sum(self._fns, kwargs))

    @property
    def variables(self) -> Tuple[str, ...]:
        """List all variables and functions referenced by this expression."""
        return self._fn.co_names

    @property
    def free_variables(self) -> Tuple[str, ...]:
        """List all the "free" variables, i.e. the ones that must be specified by arguments when
        calling the function.
        """
        return tuple(
            name for name in self.variables if not self.is_valid_function(name)
        )

    @property
    def ast(self) -> ast.AST:
        """The AST representation of this function."""
        return self._ast

    def functions(self) -> Dict[str, Callable]:
        """The dictionary of available functions callable by this function."""
        return self._fns

    def __str__(self) -> str:
        """A string representation of the expression. This may not be identical to the original."""
        return ast.unparse(self._ast)

    def is_valid_function(self, name: str) -> bool:
        """Test if the given name is a valid function for use in this expression.

        This is faster than checking if name is in self.functions().
        """
        return name in self._fns


# Below lives the meat of validation. The core idea is that we have a handler for *every* AST node
# type; some are allowed, some always fail with an error, and some have more detailed permissions
# logic. The default behavior is to fail, so that if Python adds new operator types in the future,
# they'll be banned by default (but existing operators will keep working).


def _dict_sum(*dicts: dict) -> dict:
    """Return the union of the given dicts, minimizing copies. Items later in dicts take priority
    over items earlier in dicts.

    This means that the return value may be one of the original dicts.
    """
    non_empty: Optional[dict] = None
    count_non_empty = 0
    for layer in dicts:
        if layer:
            count_non_empty += 1
            non_empty = layer

    if not count_non_empty:
        return {}
    elif count_non_empty == 1:
        assert non_empty is not None
        return non_empty

    # Actually have multiple layers to merge.
    result: dict = {}
    for layer in dicts:
        result.update(layer)
    return result


# Deliberately excluded from this list:
#   May affect flow of control: breakpoint, exit, quit
#   May allow code injection: compile, eval, exec
#   May modify state: delattr, setattr
#   May access outside data: globals
#   Not usable in expressions: classmethod, staticmethod, property
#   Affects UI or IO: input, open, print
#   No clear reason to allow: copyright, credits, help, license
# Note the getattr/hasattr lookup because the list of builtins changes with different Python
# versions.
SAFE_BUILTINS: Dict[str, Callable] = {
    name: getattr(builtins, name)
    for name in [
        # Built-in functions
        "abs",
        "aiter",
        "all",
        "anext",
        "any",
        "ascii",
        "bin",
        "bool",
        "bytearray",
        "bytes",
        "callable",
        "chr",
        "complex",
        "dict",
        "dir",
        "divmod",
        "enumerate",
        "filter",
        "float",
        "format",
        "frozenset",
        "getattr",
        "hasattr",
        "hash",
        "hex",
        "id",
        "int",
        "isinstance",
        "issubclass",
        "iter",
        "len",
        "list",
        "locals",
        "map",
        "max",
        "memoryview",
        "min",
        "next",
        "object",
        "oct",
        "ord",
        "pow",
        "range",
        "repr",
        "reversed",
        "round",
        "set",
        "slice",
        "sorted",
        "str",
        "sum",
        "super",
        "tuple",
        "type",
        "vars",
        "zip",
        # Other built-in types and so on
        "False",
        "True",
        "Ellipsis",
        "None",
        "ArithmeticError",
        "AssertionError",
        "AttributeError",
        "BaseException",
        "BlockingIOError",
        "BrokenPipeError",
        "BufferError",
        "BytesWarning",
        "ChildProcessError",
        "ConnectionAbortedError",
        "ConnectionError",
        "ConnectionRefusedError",
        "ConnectionResetError",
        "DeprecationWarning",
        "EOFError",
        "EncodingWarning",
        "EnvironmentError",
        "Exception",
        "FileExistsError",
        "FileNotFoundError",
        "FloatingPointError",
        "FutureWarning",
        "GeneratorExit",
        "IOError",
        "ImportError",
        "ImportWarning",
        "IndentationError",
        "IndexError",
        "InterruptedError",
        "IsADirectoryError",
        "KeyError",
        "KeyboardInterrupt",
        "LookupError",
        "MemoryError",
        "ModuleNotFoundError",
        "NameError",
        "NotADirectoryError",
        "NotImplemented",
        "NotImplementedError",
        "OSError",
        "OverflowError",
        "PendingDeprecationWarning",
        "PermissionError",
        "ProcessLookupError",
        "RecursionError",
        "ReferenceError",
        "ResourceWarning",
        "RuntimeError",
        "RuntimeWarning",
        "StopAsyncIteration",
        "StopIteration",
        "SyntaxError",
        "SyntaxWarning",
        "SystemError",
        "SystemExit",
        "TabError",
        "TimeoutError",
        "TypeError",
        "UnboundLocalError",
        "UnicodeDecodeError",
        "UnicodeEncodeError",
        "UnicodeError",
        "UnicodeTranslateError",
        "UnicodeWarning",
        "UserWarning",
        "ValueError",
        "Warning",
        "ZeroDivisionError",
    ]
    if hasattr(builtins, name)
}


class _ValidationContext(NamedTuple):
    expression: str
    variables: Optional[Set[str]]
    functions: Dict[str, Callable]
    allow_attribute_functions: bool

    def fail(self, node: ast.AST, error: str) -> NoReturn:
        payload = (
            (
                "<expression>",
                node.lineno,
                node.col_offset,
                self.expression,
                node.end_lineno,
                node.end_col_offset,
            )
            if sys.hexversion >= 0x030A0000
            else ("<expression>", node.lineno, node.col_offset, self.expression)
        )
        raise SyntaxError(error, payload)

    def is_valid_name(self, name: Union[str, ast.Name]) -> bool:
        if isinstance(name, ast.Name):
            name = name.id
        return (
            self.variables is None or name in self.variables or name in self.functions
        )

    def is_valid_function(self, name: str) -> bool:
        return name in self.functions

    def validate(self, node: ast.AST) -> None:
        """Validate the safety of an AST.

        We don't use ast.NodeVisitor because its recursion isn't quite flexible enough for us,
        but it's a really simple class anyway.
        """
        op = HANDLERS.get(type(node), _unknown_node)
        already_recursed = False
        if isinstance(op, str):
            self.fail(node, op)
        elif callable(op):
            already_recursed = op(node, self)

        if not already_recursed:
            for field, value in ast.iter_fields(node):
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, ast.AST):
                            self.validate(item)
                elif isinstance(value, ast.AST):
                    self.validate(value)


def _validate_name(node: ast.AST, context: _ValidationContext) -> bool:
    assert isinstance(node, ast.Name)
    if not context.is_valid_name(node):
        context.fail(node, f'Reference to unknown variable "{node.id}"')
    if not isinstance(node.ctx, ast.Load):
        context.fail(node, f'Attempt to mutate the variable "{node.id}"')
    return False


def _validate_call(node: ast.AST, context: _ValidationContext) -> bool:
    assert isinstance(node, ast.Call)
    if isinstance(node.func, ast.Name):
        if not context.is_valid_function(node.func.id):
            context.fail(node, f'Attempt to call unknown function "{node.func.id}"')
    elif isinstance(node.func, ast.Attribute):
        if not isinstance(node.func.value, ast.Name):
            context.fail(node, "Strange attribute; what's its name? Never happens.")
        if not context.is_valid_name(node.func.value):
            context.fail(
                node,
                f'Attempt to call function in unknown variable "{node.func.value.id}"',
            )
        if not context.allow_attribute_functions:
            context.fail(
                node,
                f'Attempt to call method of "{node.func.value.id}" but calling methods '
                f"of variables has been explicitly forbidden.",
            )
    else:
        context.fail(
            node, "Attempted to call something that is neither a name nor an attribute."
        )

    return False


def _validate_comprehension(node: ast.AST, context: _ValidationContext) -> bool:
    if not hasattr(node, "generators"):
        context.fail(node, f"Encountered a {type(node)} with no generators??")

    # Here we need some custom recursion, because we're defining names in an inner scope!
    child_names: List[str] = []
    for generator in node.generators:  # type: ignore
        if not isinstance(generator.target, ast.Name) or not isinstance(
            generator.target.ctx, ast.Store
        ):
            context.fail(node, "Invalid generator expression")
        if context.variables is not None and generator.target.id in context.variables:
            context.fail(
                node,
                f'The comprehension variable "{generator.target.id}" masks a variable name',
            )
        child_names.append(generator.target.id)

    # We'll modify the context recursively.
    try:
        if context.variables is not None:
            context.variables.update(child_names)

        for generator in node.generators:  # type: ignore
            context.validate(generator.iter)
            for condition in generator.ifs:
                context.validate(condition)
        if hasattr(node, "elt"):
            context.validate(node.elt)  # type: ignore
        if hasattr(node, "key"):
            context.validate(node.key)  # type: ignore
        if hasattr(node, "value"):
            context.validate(node.value)  # type: ignore

    finally:
        if context.variables is not None:
            for child_name in child_names:
                context.variables.discard(child_name)

    return True  # We've already handled recursion


def _unknown_node(node: ast.AST, context: _ValidationContext) -> bool:
    context.fail(
        node, f"Operations of type {type(node)} are not supported in Expressions."
    )
    return False


###############################################################################################
# Definition of how we validate each AST node.

_ACTION = Union[None, str, Callable[[ast.AST, _ValidationContext], bool]]
HANDLERS: Dict[Type[ast.AST], _ACTION] = {}


def _on(name: str, action: _ACTION) -> None:
    """Define what we do when we see a node of a given type. This function is here so that we
    can handle different Python versions which have different AST types. Note that this is both
    a positive and negative list for security reasons! Unknown node types are *errors* by
    default until we can manually say that they're kosher.

    The actions are:
        None -- this node is fine
        str -- this node is always an error
        function -- call this when you find such a node. The arguments are the AST node and the
            _ValidationContext; the return value should be false to allow the scanner to recurse
            through all the node's children as usual, or true if the function has already taken
            care of that itself.
    """
    if hasattr(ast, name):
        HANDLERS[getattr(ast, name)] = action


NO_ASSIGN = "Variable assignment is not permitted in expressions"
NO_DELETE = "Variable deletion is not permitted in expressions"
NO_DECLARE = "Declariung objects, classes, or functions is not permitted in expressions"
NO_IMPORT = "Importing objects is not permitted in expressions"
NO_CONTROL = "Control flow operations are not permitted in expressions"

_on("Expression", None)
_on("Module", None)
_on("FunctionType", None)
_on("Interactive", NO_CONTROL)
_on("Constant", None)
_on("FormattedValue", None)
_on("JoinedStr", None)
_on("List", None)
_on("Tuple", None)
_on("Set", None)
_on("Dict", None)
_on("Name", _validate_name)
# These three *should* be caught by _validate_name but just in case
_on("Load", None)
_on("Store", NO_ASSIGN)
_on("Del", NO_DELETE)
_on("Starred", None)
_on("Expr", None)
_on("UnaryOp", None)
_on("UAdd", None)
_on("USub", None)
_on("Not", None)
_on("Invert", None)
_on("BinOp", None)
_on("Add", None)
_on("Sub", None)
_on("Mult", None)
_on("Div", None)
_on("FloorDiv", None)
_on("Mod", None)
_on("Pow", None)
_on("LShift", None)
_on("RShift", None)
_on("BitOr", None)
_on("BitXor", None)
_on("BitAnd", None)
_on("MatMult", None)
_on("BoolOp", None)
_on("And", None)
_on("Or", None)
_on("Compare", None)
_on("Eq", None)
_on("NotEq", None)
_on("Lt", None)
_on("LtE", None)
_on("Gt", None)
_on("GtE", None)
_on("Is", None)
_on("IsNot", None)
_on("n", None)
_on("NotIn", None)
_on("Call", _validate_call)
_on("keyword", None)
_on("IfExp", None)
_on("Attribute", None)  # Validated by the validation of its child name
_on("NamedExpr", NO_ASSIGN)
_on("Subscript", None)
_on("Slice", None)
_on("ListComp", _validate_comprehension)
_on("SetComp", _validate_comprehension)
_on("GeneratorExp", _validate_comprehension)
_on("DictComp", _validate_comprehension)
_on("comprehension", None)
_on("Assign", NO_ASSIGN)
_on("AnnAssign", NO_ASSIGN)
_on("AugAssign", NO_ASSIGN)
_on("Raise", NO_CONTROL)
_on("Assert", NO_CONTROL)
_on("Delete", NO_DELETE)
_on("Pass", None)
_on("Import", NO_IMPORT)
_on("ImportFrom", NO_IMPORT)
_on("alias", None)
_on("If", None)
_on("For", None)
_on("While", None)
_on("Break", None)
_on("Continue", None)
_on("Try", None)
_on("TryStar", None)
_on("ExceptHandler", None)
_on("With", None)
_on("withitem", None)
_on("Match", None)
_on("match_case", None)
_on("MatchValue", None)
_on("MatchSingleton", None)
_on("MatchSequence", None)
_on("MatchStar", None)
_on("MatchMapping", None)
_on("MatchClass", None)
_on("MatchAs", None)
_on("MatchOr", None)
_on("FunctionDef", NO_DECLARE)
_on("Lambda", None)
_on("arguments", None)
_on("arg", None)
_on("Return", NO_CONTROL)
_on("Yield", NO_CONTROL)
_on("YieldFrom", NO_CONTROL)
_on("Global", "Modifying global variables is not permitted in expressions")
_on("Nonlocal", "Modifying nonlocal variables is not permitted in expressions")
_on("ClassDef", NO_DECLARE)
_on("AsyncFunctionDef", NO_DECLARE)
_on("Await", None)
_on("AsyncFor", None)
_on("AsyncWith", None)
