import sys
import unittest
from pathlib import Path
from typing import List

from pyppin.os.bulk_import import bulk_import

from .bulk_import_test_data._def import ImportableThing

TEST_PATH = Path(__file__).parent


class BulkImportTest(unittest.TestCase):
    def testBulkImport(self) -> None:
        self.assertEqual({}, ImportableThing.subclasses())  # type: ignore

        names = bulk_import(TEST_PATH.joinpath("bulk_import_test_data"), root=TEST_PATH)

        self.assertEqual(
            ["Class1", "Class2"],
            sorted(list(ImportableThing.subclasses())),  # type: ignore
        )

        # Clean up
        ImportableThing._registry = {}
        for name in names.keys():
            del sys.modules[name]
        self.assertEqual([], list(ImportableThing.subclasses()))  # type: ignore

    def testVisitor(self) -> None:
        # The visitor is called on every file we see, primarily for its side effects; here we
        # just record them. Returning false for class1.py also proves it can exclude a file.
        visited: List[str] = []

        def visitor(p: Path) -> bool:
            visited.append(p.name)
            return p.name != "class1.py"

        names = bulk_import(
            TEST_PATH.joinpath("bulk_import_test_data"), root=TEST_PATH, visitor=visitor
        )

        # The visitor saw every file in the directory, including the non-importable (.txt)
        # ones and the underscore files (the exclude patterns only stop directory recursion).
        self.assertEqual(
            [
                "__init__.py",
                "_def.py",
                "class1.py",
                "class2.py",
                "class3.txt",
                "notpython.txt",
            ],
            sorted(visited),
        )

        # ...but only class2 was actually imported: class1 was vetoed by the visitor, and the
        # .txt files aren't importable Python.
        self.assertEqual(
            ["Class2"],
            sorted(list(ImportableThing.subclasses())),  # type: ignore
        )

        # Clean up
        ImportableThing._registry = {}
        for name in names.keys():
            del sys.modules[name]
        self.assertEqual([], list(ImportableThing.subclasses()))  # type: ignore


if __name__ == "__main__":
    unittest.main()
