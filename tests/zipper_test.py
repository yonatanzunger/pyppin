import unittest

from pyppin.zipper import ZipSource, zipper


class ZipperTest(unittest.TestCase):
    def testSimpleZip(self) -> None:
        self.assertEqual(
            [
                (1, 1, 1),
                (2, None, 2),
                (3, 3, 3),
                (4, None, 4),
                (5, 5, 5),
                (7, 7, None),
            ],
            list(zipper([1, 3, 5, 7], [1, 2, 3, 4, 5])),
        )

    def testWithOptions(self) -> None:
        self.assertEqual(
            [
                (2, 4, "two"),
                (5, 25, "five"),
                (7, None, "seven"),
            ],
            list(
                zipper(
                    ZipSource([1, 2, 3, 4, 5], value=lambda x: x * x),
                    ZipSource(
                        [
                            (2, "two"),
                            (5, "five"),
                            (7, "seven"),
                        ],
                        key=lambda x: x[0],
                        value=lambda x: x[1],
                        required=True,
                    ),
                )
            ),
        )

    def testWithAuxSource(self) -> None:
        # Same test as testWithOptions, but use an aux source to generate the squares.
        self.assertEqual(
            [
                (2, 4, "two"),
                (5, 25, "five"),
                (7, 49, "seven"),
            ],
            list(
                zipper(
                    ZipSource.aux(lambda x: x * x),
                    ZipSource(
                        [
                            (2, "two"),
                            (5, "five"),
                            (7, "seven"),
                        ],
                        key=lambda x: x[0],
                        value=lambda x: x[1],
                        required=True,
                    ),
                )
            ),
        )

    def testPureAuxSources(self) -> None:
        # Just aux sources yields nothing.
        self.assertEqual(
            [], list(zipper(ZipSource.aux(lambda x: x), ZipSource.aux(lambda x: x * x)))
        )

    # TODO many more!


if __name__ == "__main__":
    unittest.main()
