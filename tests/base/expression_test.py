import unittest

from pyppin.base.expression import Expression


class ExpressionTest(unittest.TestCase):
    def test_simple_expression(self) -> None:
        e = Expression('x + 3', variables=['x'])
        self.assertEqual(5, e({'x': 2}))

        # The expression makes no sense if x is a string!
        with self.assertRaises(TypeError):
            e({'x': 'foo'})

        # No definition for x!
        with self.assertRaises(NameError):
            e({})

    def test_forbidden_names(self) -> None:
        with self.assertRaises(SyntaxError):
            Expression('y + 3', variables=['x'])

        with self.assertRaises(SyntaxError):
            Expression('open(x)', variables=['x'])

        # Prevent cleverness
        with self.assertRaises(SyntaxError):
            Expression('compile(f"open({x})")', variables=['x'])

    def test_attempt_modify(self) -> None:
        with self.assertRaises(SyntaxError):
            Expression('x += 2', variables=['x'])

        with self.assertRaises(SyntaxError):
            Expression('setattr(x, "foo", None)', variables=['x'])

        with self.assertRaises(SyntaxError):
            Expression('import sys', variables=[])

    def test_comprehension(self) -> None:
        e = Expression('[x + 3 for x in src]', variables=['src'])
        self.assertEqual([4, 5, 6], e({'src': [1, 2, 3]}))

        with self.assertRaises(SyntaxError):
            Expression('[y + 3 for x in src]', variables=['src'])

    def test_builtin_functions(self) -> None:
        e = Expression('list(zip(x, y))', variables=['x', 'y'])
        self.assertEqual(
            [(1, 'a'), (2, 'b'), (3, 'c')], e({'x': [1, 2, 3], 'y': ['a', 'b', 'c', 'd']})
        )

    def test_passed_functions(self) -> None:
        def foo(x: int) -> int:
            return x + 3

        e = Expression('foo(x) + 2', variables=['x', 'foo'])
        self.assertEqual(5, e({'x': 0, 'foo': foo}))

    def test_attribute_functions(self) -> None:
        class DataObject(object):
            def __init__(self, value: int) -> None:
                self.value = value

            @property
            def aprop(self) -> str:
                return f'foo: {self.value}'

            def afunc(self) -> str:
                return f'bar: {self.value}'

        data = DataObject(5)

        e = Expression('f"{x.value} => {x.aprop}"', variables=['x'])
        self.assertEqual('5 => foo: 5', e({'x': data}))

        with self.assertRaises(SyntaxError):
            Expression('f"{x.value} => {x.afunc()}"', variables=['x'])

        e2 = Expression(
            'f"{x.value} => {x.afunc()}"', variables=['x'], allow_attribute_functions=True
        )
        self.assertEqual('5 => bar: 5', e2({'x': data}))


# Built-in functions
# Passed functions
# Attribute functions
