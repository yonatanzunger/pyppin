import unittest
from collections import defaultdict
from typing import Dict

from pyppin.containers.iterators import sample, split
from pyppin.math import within
from pyppin.math.histogram import Histogram


class IteratorsTest(unittest.TestCase):
    def test_split(self) -> None:
        self.assertEqual(
            {0: [0, 3, 6], 1: [1, 4, 7], 2: [2, 5, 8]}, split(range(9), lambda x: x % 3)
        )

    def test_sample_short(self) -> None:
        self.assertEqual([0, 1, 2, 3], sample(range(4), 10))

    def test_sample(self) -> None:
        # Do TEST_COUNT passes of reservoir sampling of SAMPLE_COUNT items out of a stream of
        # STREAM_LENGTH items, and verify that the statistics make sense.
        TEST_COUNT = 1000
        STREAM_LENGTH = 1000
        SAMPLE_COUNT = 100

        # Map from N ∈ [0, STREAM_LENGTH) to the number of times N was picked
        counts: Dict[int, int] = defaultdict(int)

        for test_pass in range(TEST_COUNT):
            result = sample(range(STREAM_LENGTH), SAMPLE_COUNT)
            self.assertEqual(SAMPLE_COUNT, len(result))
            for value in result:
                counts[value] += 1

        # See if counts is uniform.
        histogram = Histogram()
        for count in counts.values():
            histogram.add(count)

        # We expect this curve to be more or less Gaussian, with mean (TEST_COUNT * SAMPLE_COUNT) /
        # STREAM_LENGTH, and standard deviation XXX.
        expected_mean = TEST_COUNT * SAMPLE_COUNT / STREAM_LENGTH
        self.assertTrue(
            within(histogram.mean, 0.99 * expected_mean, 1.01 * expected_mean),
            f'Distribution out of range: Got mean {histogram.mean}, expected {expected_mean}',
        )
        self.assertLess(histogram.standard_deviation, 25)
