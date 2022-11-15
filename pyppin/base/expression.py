import ast
from typing import (
    Any,
    Callable,
    Container,
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

# XXX
# - finish documentation
# - can you define a function etc?
# - warning about crashing Python interpreter


class Expression(object):
    def __init__(
        self,
        expression: str,
        *,
        variables: Container[str],
        allow_attribute_functions: bool = False,
    ) -> None:
        """Expression implements "safe" evaluation of user-entered Python expressions.

        Args:
            expression: A Python expression to be turned into this object. This expression may use
                any of the Python language, any of the "safe" built-in functions listed below in
                SAFE_BUILTINS, and any variables or functions listed in the ``variables`` argument.
                It may not engage in I/O
            variables: A list of the names of all variables and functions which the expression
                should be allowed to access.
            allow_attribute_functions: If you have allowed a variable 'foo', and foo.bar is a
                callable, then by default calls to foo.bar(...) will *not* be allowed. (Because
                otherwise you could only pass an object to the expression by also allowing the
                user to call arbitrary methods of it!) If you set this to true, such calls are
                permitted.
                Note that attribute *properties* are always permitted.
        """

        """An Expression is a "safe" version of a Python expression that can be parsed from
        user input, and then evaluated. Expressions can contain all of the "basic" Python
        operators, like arithmetic, array access, and so on, and can reference variables
        which you provide at evaluation time. They are deliberately secured so that "dangerous"
        operations (like ones that could mutate state) are not permitted; this is a sanitizer.

        So for example, you could have a user-entered expression to compute a score for a Wombat,
        then iterate over a database of Wombats and return the value for each of these.

        Args:
            expression: A Python expression.
            variables: The set of variable and function names which are allowed within the
                expression. The "safe" Python built-in functions (abs, max, etc) are always
                allowed. You will need to pass a dict containing the actual values of these
                variables and functions when evaluating the expression.
            allow_attribute_functions: If you have an allowed variable 'foo', and foo.bar is
                a function, by default calls to it will *not* be allowed (for safety!); if you
                set this to true, it is allowed.

        Raises:
            SyntaxError: If the expression cannot be parsed, or if the expression attempted to
                do something forbidden, like reference an unknown variable.
            ValueError: If the expression string contains NUL bytes for some reason.
        """
        self._ast = ast.parse(expression, mode='eval')
        _validate(self._ast, expression, set(variables), allow_attribute_functions)
        self._fn = compile(self._ast, filename='<string>', mode='eval')
        if self._fn.co_argcount:
            raise SyntaxError(
                'Expression expected arguments', ('<string>', 1, 0, expression, 1, len(expression))
            )

    def __call__(self, variables: Optional[Dict[str, Any]] = None) -> Any:
        """Evaluate the expression, giving it access to any indicated variables.

        Args:
            variables: Values for all the variables referenced by the expression. Every value in
                self.variables should be found here!

        Returns: The evaluated value of the expression.

        Raises:
            Any exception raised by the expression itself.
            NameError: If some variable referenced was not given in variables.
        """
        return eval(self._fn, {}, variables)

    @property
    def variables(self) -> Tuple[str, ...]:
        """List all variables referenced by this expression."""
        return self._fn.co_names

    @property
    def ast(self) -> ast.AST:
        return self._ast

    def __str__(self) -> str:
        return ast.unparse(self._ast)


# Below lives the meat of validation. The core idea is that we have a handler for *every* AST node
# type; some are allowed, some always fail with an error, and some have more detailed permissions
# logic. The default behavior is to fail, so that if Python adds new operator types in the future,
# they'll be banned by default (but existing operators will keep working).


class _ValidationContext(NamedTuple):
    expression: str
    variables: Set[str]
    allow_attribute_functions: bool

    def fail(self, node: ast.AST, error: str) -> NoReturn:
        raise SyntaxError(
            error,
            (
                '<string>',
                node.lineno,
                node.col_offset,
                self.expression,
                node.end_lineno,
                node.end_col_offset,
            ),
        )


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


def _validate_name(node: ast.AST, context: _ValidationContext) -> bool:
    assert isinstance(node, ast.Name)
    if node.id not in SAFE_BUILTINS and node.id not in context.variables:
        context.fail(node, f'Reference to unknown variable "{node.id}"')
    if not isinstance(node.ctx, ast.Load):
        context.fail(node, f'Attempt to mutate the variable "{node.id}"')
    return False


def _unknown_node(node: ast.AST, context: _ValidationContext) -> bool:
    context.fail(node, f'Operations of type {type(node)} are not supported in Expressions.')
    return False


# Deliberately excluded from this list:
#   May affect flow of control: breakpoint, exit, quit
#   May allow code injection: compile, eval, exec
#   May modify state: delattr, setattr
#   May access outside data: globals
#   Not usable in expressions: classmethod, staticmethod, property
#   Affects UI or IO: input, open, print
#   No clear reason to allow: copyright, credits, help, license
SAFE_BUILTINS = {
    'abs',
    'aiter',
    'all',
    'anext',
    'any',
    'ascii',
    'bin',
    'bool',
    'bytearray',
    'bytes',
    'callable',
    'chr',
    'complex',
    'dict',
    'dir',
    'divmod',
    'enumerate',
    'filter',
    'float',
    'format',
    'frozenset',
    'getattr',
    'hasattr',
    'hash',
    'hex',
    'id',
    'int',
    'isinstance',
    'issubclass',
    'iter',
    'len',
    'list',
    'locals',
    'map',
    'max',
    'memoryview',
    'min',
    'next',
    'object',
    'oct',
    'ord',
    'pow',
    'range',
    'repr',
    'reversed',
    'round',
    'set',
    'slice',
    'sorted',
    'str',
    'sum',
    'super',
    'tuple',
    'type',
    'vars',
    'zip',
}


def _validate_call(node: ast.AST, context: _ValidationContext) -> bool:
    assert isinstance(node, ast.Call)
    if isinstance(node.func, ast.Name):
        if not (node.func.id in SAFE_BUILTINS or node.func.id in context.variables):
            context.fail(node, f'Attempt to call unknown function "{node.func.id}"')
    elif isinstance(node.func, ast.Attribute):
        if not isinstance(node.func.value, ast.Name):
            context.fail(node, "Strange attribute; what's its name? Never happens.")
        if node.func.value.id not in context.variables:
            context.fail(
                node,
                f'Attempt to call function in unknown variable "{node.func.value.id}"',
            )
        if not context.allow_attribute_functions:
            context.fail(
                node,
                f'Attempt to call method of "{node.func.value.id}" but calling methods '
                f'of variables has been explicitly forbidden.',
            )
    else:
        context.fail(node, "Attempted to call something that is neither a name nor an attribute.")

    return False


def _validate_comprehension(node: ast.AST, context: _ValidationContext) -> bool:
    if not hasattr(node, 'generators'):
        context.fail(node, f'Encountered a {type(node)} with no generators??')

    # Here we need some custom recursion, because we're defining names in an inner scope!
    child_names: List[str] = []
    for generator in node.generators:
        if not isinstance(generator.target, ast.Name) or not isinstance(
            generator.target.ctx, ast.Store
        ):
            context.fail(node, 'Invalid generator expression')
        if generator.target.id in context.variables:
            context.fail(
                node, f'The comprehension variable "{generator.target.id}" masks a variable name'
            )
        child_names.append(generator.target.id)

    # We'll modify the context recursively.
    try:
        context.variables.update(child_names)

        for generator in node.generators:
            _validate_recursive(generator.iter, context)
            for condition in generator.ifs:
                _validate_recursive(condition, context)
        if hasattr(node, 'elt'):
            _validate_recursive(node.elt, context)
        if hasattr(node, 'key'):
            _validate_recursive(node.key, context)
        if hasattr(node, 'value'):
            _validate_recursive(node.value, context)

    finally:
        for child_name in child_names:
            context.variables.discard(child_name)

    return True


NO_ASSIGN = 'Variable assignment is not permitted in expressions'
NO_DELETE = 'Variable deletion is not permitted in expressions'
NO_DECLARE = 'Declariung objects, classes, or functions is not permitted in expressions'
NO_IMPORT = 'Importing objects is not permitted in expressions'
NO_CONTROL = 'Control flow operations are not permitted in expressions'

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
_on("Global", 'Modifying global variables is not permitted in expressions')
_on("Nonlocal", 'Modifying nonlocal variables is not permitted in expressions')
_on("ClassDef", NO_DECLARE)
_on("AsyncFunctionDef", NO_DECLARE)
_on("Await", None)
_on("AsyncFor", None)
_on("AsyncWith", None)


class _Validator(ast.NodeVisitor):
    def __init__(self, context: _ValidationContext) -> None:
        self.context = context

    def visit(self, node: ast.AST) -> None:
        op = HANDLERS.get(type(node), _unknown_node)
        if isinstance(op, str):
            self.context.fail(node, op)
        elif callable(op):
            child_names = op(node, self.context)

        if child_names:
            for child_name in child_names:
                # This isn't *technically* a Python error but it's a bug magnet so we forbid it.
                if child_name in self.context.variables:
                    self.context.fail(
                        node, f'The comprehension variable "{child_name}" masks a variable name'
                    )

        # Because this class is used just as a single-pass verifier, modifying our own instance
        # variables is safe. Note that we also just verified that self.context.variables and
        # child_names are disjoint.
        try:
            if child_names:
                self.context.variables.update(child_names)
            self.generic_visit(node)
        finally:
            for child_name in child_names or tuple():
                self.context.variables.discard(child_name)


def _validate(
    tree: ast.AST, expression: str, variables: Set[str], allow_attribute_functions: bool
) -> None:
    """Validate the safety of an AST.

    We don't use ast.NodeVisitor because its recursion isn't quite flexible enough for us, but it's
    a really simple class anyway.
    """
    context = _ValidationContext(expression, variables, allow_attribute_functions)
    _validate_recursive(tree, context)


def _validate_recursive(node: ast.AST, context: _ValidationContext) -> None:
    op = HANDLERS.get(type(node), _unknown_node)
    already_recursed = False
    if isinstance(op, str):
        context.fail(node, op)
    elif callable(op):
        already_recursed = op(node, context)

    if not already_recursed:
        for field, value in ast.iter_fields(node):
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, ast.AST):
                        _validate_recursive(item, context)
            elif isinstance(value, ast.AST):
                _validate_recursive(value, context)
