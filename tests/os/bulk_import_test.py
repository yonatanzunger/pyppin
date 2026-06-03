import unittest
from pathlib import Path
import sys

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

    def testVisitorAllowsClass3(self) -> None:
        def visitor(p: Path) -> bool:
            return p.suffix == ".py" or p.name == "class3.txt"

        names = bulk_import(
            TEST_PATH.joinpath("bulk_import_test_data"), root=TEST_PATH, visitor=visitor
        )

        self.assertEqual(
            ["Class1", "Class2", "Class3"],
            sorted(list(ImportableThing.subclasses())),  # type: ignore
        )

        # Clean up
        ImportableThing._registry = {}
        for name in names.keys():
            del sys.modules[name]
        self.assertEqual([], list(ImportableThing.subclasses()))  # type: ignore


if __name__ == "__main__":
    unittest.main()
