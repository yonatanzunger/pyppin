import unittest
from typing import List

from pyppin.testing.interact import interact

global_variable = 1


class InteractTest(unittest.TestCase):
    def testCannotModifyLocalVariables(self) -> None:
        # Test that we can change the value of a local variable
        def foo(commands: List[str]) -> int:
            bar = 1
            interact(_test_commands=commands)
            return bar

        # Now 'bar' should *not* get changed!
        self.assertEqual(1, foo(["bar = 2"]))

    def testCannotAddLocalVariables(self) -> None:
        interact(_test_commands=["bar = 3"])
        self.assertFalse("bar" in locals())

    def testCannotModifyGlobalVariables(self) -> None:
        global global_variable
        interact(
            _test_commands=["global_variable = 2"],
        )
        self.assertEqual(1, global_variable)

    def testCannotDeleteLocalVariable(self) -> None:
        bar = 1
        quux = 2
        interact(_test_commands=["del bar"])
        self.assertEqual(2, quux)
        self.assertEqual(1, bar)


if __name__ == "__main__":
    unittest.main()
