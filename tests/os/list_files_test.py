import os
import unittest
from tempfile import TemporaryDirectory

from pyppin.os.list_files import list_files


class ListFilesTest(unittest.TestCase):
    def testListFiles(self) -> None:
        # We're going to create our test environment here, rather than storing it as data in the git
        # repository. This is because we deliberately want to create weird things like infinite-loop
        # symlinks, which make git very unhappy.
        with TemporaryDirectory() as root:
            with open(f"{root}/foo.txt", "w") as foo:
                foo.write("foo\n")
            os.symlink(f"{root}/foo.txt", f"{root}/bar.txt")
            os.mkdir(f"{root}/skipme")
            with open(f"{root}/skipme/not_seen.txt", "w") as not_seen:
                not_seen.write("skipme\n")
            os.mkdir(f"{root}/subdir")
            with open(f"{root}/subdir/quux.txt", "w") as quux:
                quux.write("quux\n")
            # Yee-haw!
            os.symlink("..", f"{root}/subdir/loop")

            # OK, now let's see if we can list this mess correctly. Note that the only "real" files
            # are the ones we generated with calls to write() above; everything else is a symlink or
            # directory that should not show up in the output.

            # Set up an absolute path to make it as hard as possible for relative_to to work below.
            # root = Path(__file__).parent.joinpath("list_files_test_data").resolve()
            found = list_files(root, select=lambda path: "skip" not in path.name)

            # The fact that relative_to will work in this case is a guaranteed invariant of
            # list_files!
            relative = [str(path.relative_to(root)) for path in found]

            # Things that do *not* show up in this output:
            #   - bar.txt is a symlink to foo.txt, so we don't yield it twice.
            #   - subdir/loop is an infinite-loop symlink, and we don't fall into that trap.
            #   - skipme/not_seen.txt is skipped because of the select function.
            self.assertEqual(["foo.txt", "subdir/quux.txt"], sorted(relative))


if __name__ == "__main__":
    unittest.main()
