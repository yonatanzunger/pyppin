import unittest
from pathlib import Path

from pyppin.list_files import list_files


class ListFilesTest(unittest.TestCase):
    def testListFiles(self) -> None:
        # Set up an absolute path to make it as hard as possible for relative_to to work below.
        root = Path(__file__).parent.joinpath("list_files_test_data").resolve()
        found = list_files(root, select=lambda path: "skip" not in path.name)

        # The fact that relative_to will work in this case is a guaranteed invariant of list_files!
        relative = [str(path.relative_to(root)) for path in found]

        # Things that do *not* show up in this output:
        #   - bar.txt is a symlink to foo.txt, so we don't yield it twice.
        #   - subdir/loop is an infinite-loop symlink, and we don't fall into that trap.
        #   - skipme/not_seen.txt is skipped because of the select function.
        self.assertEqual(["foo.txt", "subdir/quux.txt"], sorted(relative))


if __name__ == "__main__":
    unittest.main()
