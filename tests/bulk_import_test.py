import unittest
from pathlib import Path

from pyppin.bulk_import import bulk_import

from .bulk_import_test_data._def import ImportableThing

TEST_PATH = Path(__file__).parent


class BulkImportTest(unittest.TestCase):
    def testBulkImport(self) -> None:
        self.assertEqual({}, ImportableThing.subclasses())

        bulk_import(TEST_PATH.joinpath("bulk_import_test_data"), root=TEST_PATH)

        self.assertEqual(
            ["Class1", "Class2"], sorted(list(ImportableThing.subclasses()))
        )


if __name__ == "__main__":
    unittest.main()
