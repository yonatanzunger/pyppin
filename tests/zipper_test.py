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

    def testOneInput(self) -> None:
        self.assertEqual([1, 2, 3, 4], list(zipper([1, 2, 3, 4], yieldKeys=False)))

    def testZeroInputs(self) -> None:
        self.assertEqual([], list(zipper()))

    def testUnsortedInputRaisesError(self) -> None:
        with self.assertRaises(IndexError):
            list(zipper([1, 3, 2, 4]))

        # NB: We exclude lists that aren't strictly sorted because the correct output to give
        # in this case is highly nonobvious. If two of the input lists have multiple values
        # for a given key, what do we output there? The outer product? Some parallelization?
        with self.assertRaises(IndexError):
            list(zipper([1, 1, 2, 3]))

    def testValueDecorator(self) -> None:
        self.assertEqual(
            [(1, "a_1"), (2, "a_2"), (3, "a_3"), (4, "a_4")],
            list(zipper(ZipSource([1, 2, 3, 4], value=lambda x: f"a_{x}"))),
        )

    def testKeyDecorator(self) -> None:
        self.assertEqual(
            [("a_1", 1), ("a_2", 2), ("a_3", 3), ("a_4", 4)],
            list(zipper(ZipSource([1, 2, 3, 4], key=lambda x: f"a_{x}"))),
        )

    def testThreeItems(self) -> None:
        self.assertEqual(
            [
                (1, "a_1", None, "c_1"),
                (2, None, "b_2", "c_2"),
                (3, "a_3", "b_3", "c_3"),
                (4, "a_4", "b_4", None),
            ],
            list(
                zipper(
                    ZipSource([1, 3, 4], value=lambda x: f"a_{x}"),
                    ZipSource([2, 3, 4], value=lambda x: f"b_{x}"),
                    ZipSource([1, 2, 3], value=lambda x: f"c_{x}"),
                )
            ),
        )

    def testMissingValue(self) -> None:
        self.assertEqual(
            [
                (1, "a_1", False, "c_1"),
                (2, "noa_2", "b_2", "c_2"),
                (3, "a_3", "b_3", "c_3"),
                (4, "a_4", "b_4", "bleah"),
            ],
            list(
                zipper(
                    ZipSource(
                        [1, 3, 4],
                        value=lambda x: f"a_{x}",
                        missing=lambda x: f"noa_{x}",
                    ),
                    ZipSource([2, 3, 4], value=lambda x: f"b_{x}", missingValue=False),
                    ZipSource(
                        [1, 2, 3], value=lambda x: f"c_{x}", missingValue="bleah"
                    ),
                )
            ),
        )

    def testMultiMissingValues(self) -> None:
        with self.assertRaises(AssertionError):
            list(zipper(ZipSource([1, 2, 3], required=True, missingValue=3)))

        with self.assertRaises(AssertionError):
            list(
                zipper(
                    ZipSource([1, 2, 3], missing=lambda x: f"foo_{x}", missingValue=3)
                )
            )

    def testPureAuxSources(self) -> None:
        # Just aux sources yields nothing.
        self.assertEqual(
            [], list(zipper(ZipSource.aux(lambda x: x), ZipSource.aux(lambda x: x * x)))
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

    def testGapsAtStartAndEnd(self) -> None:
        self.assertEqual(
            [
                (1, None, "b_1", "c_1"),
                (2, None, "b_2", "c_2"),
                (3, "a_3", "b_3", None),
                (4, "a_4", "b_4", None),
            ],
            list(
                zipper(
                    ZipSource([3, 4], value=lambda x: f"a_{x}"),
                    ZipSource([1, 2, 3, 4], value=lambda x: f"b_{x}"),
                    ZipSource([1, 2], value=lambda x: f"c_{x}"),
                )
            ),
        )

    def testEarlyExitRequiredSource(self) -> None:
        self.assertEqual(
            [
                (1, None, "b_1", "c_1"),
                (2, None, "b_2", "c_2"),
            ],
            list(
                zipper(
                    ZipSource([3, 4], value=lambda x: f"a_{x}"),
                    ZipSource([1, 2, 3, 4], value=lambda x: f"b_{x}"),
                    ZipSource([1, 2], value=lambda x: f"c_{x}", required=True),
                )
            ),
        )


if __name__ == "__main__":
    unittest.main()
