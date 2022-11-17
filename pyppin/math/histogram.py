"""A flexible class for managing, computing with, and plotting histograms.

This is an example ASCII plot, from the histogram used in the ``pyppin.iterators.sample``
unittest::

        |
        |
        |
        |
    0.0 +
        |                                                         #
        |                                                         ##
        |                                                         ##
        |                                                         ##
    0.0 +                                                         ###
        |                                                       # ###
        |                                                       # ###
        |                                                       # ### #
        |                                                       # #####
    0.0 +                                                      ## ######
        |                                                      ## ######
        |                                                      ## ######
        |                                                      ## ######
        |                                                      ## ######
    0.0 +                                                    ###########
        |                                                    ############
        |                                                    #############
        |                                                   ###############
        |                                                   ###############
    0.0 +                                                   ###############
        |                                                  ################
        |                                                  ################
        |                                                  ################
        |                                                  ################
    0.0 +                                                 #################
        |                                                 ###################
        |                                                 ####################
        |                                               # ####################
        |                                               # ####################
    0.0 +                                             # # ##################### #
        |                                             # ####################### #
        |                                           # # #########################
        ++------+------+------+------+------+------+------+------+------+------+----
         0.0    12.1   24.2   36.3   48.4   60.5   72.6   84.8   96.9   109.0  121.1
"""

import math
from functools import cached_property
from typing import Callable, List, Optional, Tuple

from pyppin.base import assert_not_none
from pyppin.math import round_up_to
from pyppin.math.functions import Interpolate, PiecewiseConstant
from pyppin.math.plot_ascii import AxisOptions, plot_ascii

# TODO add "units" and plot them as axis labels


class Histogram(object):
    def __init__(self, bucketing: Optional["Bucketing"] = None) -> None:
        """A histogram of numeric values.

        Args:
            bucketing: Parameters to control how values are assigned to buckets.
        """
        self.bucketing = bucketing or Bucketing()
        self.data: List[int] = []
        self._count: int = 0
        self._total: float = 0
        self._total_squared: float = 0
        # Store these separately from the buckets because we sometimes want exact values.
        self._max: float = 0
        self._min: float = 0

    def add(self, value: float, count: int = 1) -> None:
        """Add a value to the histogram.

        Args:
            value: The value to add.
            count: The number of times to add this value.
        """
        bucket = self.bucketing.bucket(value)
        if bucket >= len(self.data):
            self.data.extend([0] * (bucket - len(self.data) + 1))

        self.data[bucket] += count
        self._count += count
        self._total += count * value
        self._total_squared += count * value * value
        self._max = max(self._max, value)
        self._min = min(self._min, value)

    def combine(self, other: "Histogram") -> None:
        """Add another histogram to this histogram."""
        assert self.bucketing == other.bucketing
        if len(self.data) < len(other.data):
            self.data.extend([0] * (len(other.data) - len(self.data)))
        for index, value in enumerate(other.data):
            self.data[index] += value
        self._count += other._count
        self._total += other._total
        self._total_squared += other._total_squared
        self._max = max(self._max, other.max)
        self._min = min(self._min, other.min)

    @property
    def min(self) -> float:
        """The minimum value found in this histogram."""
        return self._min

    @property
    def max(self) -> float:
        """The maximum value found in this histogram."""
        return self._max

    @property
    def count(self) -> int:
        """The total number of values in this histogram."""
        return self._count

    @property
    def total(self) -> float:
        """The sum of values in this histogram."""
        return self._total

    @property
    def mean(self) -> float:
        """The mean value of the data."""
        return self._total / self._count

    def percentile(self, n: float) -> float:
        """Return the value at the Nth percentile of this histogram, with n in [0, 100]."""
        if n <= 0:
            return self._min
        if n >= 100:
            return self._max
        target_count = int(self._count * n / 100)
        current_count = 0
        for bucket, count in enumerate(self.data):
            if count + current_count >= target_count:
                # We found it! Let's interpolate the position we need within the bucket.
                previous_value = (
                    self._min
                    if bucket == 0
                    else self.bucketing.value_for_bucket(bucket - 1)
                )
                current_value = self.bucketing.value_for_bucket(bucket)
                fraction = (target_count - current_count) / count
                return previous_value + fraction * (current_value - previous_value)
            current_count += count

        raise RuntimeError("Never happens!")

    @property
    def median(self) -> float:
        """The median (50th percentile) value of the data."""
        return self.percentile(50)

    @property
    def variance(self) -> float:
        """The distribution variance of the data."""
        mean = self.mean
        mean_square = self._total_squared / self._count
        return mean_square - mean * mean

    @property
    def standard_deviation(self) -> float:
        """The standard deviation of the data.

        Reminder: If your data doesn't follow a Gaussian distribution, this is not going to give you
        a very meaningful number.
        """
        return math.sqrt(self.variance)

    def plot_ascii(
        self,
        width: int = 100,
        height: int = 0,
        min_percentile: float = 0,
        max_percentile: float = 100,
        raw_counts: bool = False,
    ) -> str:
        """Generate an ASCII plot of the histogram.

        Args:
            width, height: The dimensions of the plot, in characters. The height defaults
                to half the width.
            min_percentile, max_percentile: The subrange of the histogram to include.
            raw_counts: If True, plot the raw bucket counts. If False (the default), plot the
                probability distribution function.
        """
        return plot_ascii(
            data=self.histogram_values() if raw_counts else self.pdf(),
            width=width,
            height=height,
            x_axis=AxisOptions(
                min=self.percentile(min_percentile), max=self.percentile(max_percentile)
            ),
            vfill=True,
        )

    def histogram_values(self) -> Callable[[float], float]:
        """Return a function that looks like the histogram itself: For each value X, it returns
        the count in the bucket containing X.

        Note that this is *not* the same as the PDF, because buckets do not all have the same width!
        """
        return PiecewiseConstant(
            [
                (
                    self.bucketing.value_for_bucket(bucket),
                    count,
                )
                for bucket, count in enumerate(self.data)
            ]
        )

    def pdf(self) -> Callable[[float], float]:
        """Return the probability distribution function inferred from this histogram."""
        # For each bucket, the probability of any given *value* in the bucket is the count divided
        # by the bucket width. That's the key difference between the PDF and the raw histogram data!
        data = [
            (
                self.bucketing.value_for_bucket(bucket),
                count / (self._count * self.bucketing.bucket_width(bucket)),
            )
            for bucket, count in enumerate(self.data)
        ]
        return Interpolate(data)

    def cdf(self) -> Callable[[float], float]:
        """Return the cumulative distribution function inferred from this histogram."""
        data: List[Tuple[float, float]] = []
        last_count = 0.0
        for bucket, count in enumerate(self.data):
            last_count += count / (self._count * self.bucketing.bucket_width(bucket))
            data.append((self.bucketing.value_for_bucket(bucket), last_count))
        return Interpolate(data)


class Bucketing(object):
    """Define the shapes of the buckets that we will use for the histogram.

    We use linear/exponential bucketing: linear buckets (i.e. [0->n) [n->2n) [2n->3n)) up to some
    initial limit, and beyond that exponential buckets ([m->kn), [kn->k²n), [k²n, k³n)).

    Args:
        max_linear_value: The value at which we switch from linear to exponential buckets,
            or None to use linear values for everything.
        linear_steps: The interval size for linear values.
        exponential_multiplier: The multiplication factor for exponential values.
    """

    def __init__(
        self,
        max_linear_value: Optional[float] = None,
        linear_steps: float = 1,
        exponential_multiplier: float = 2,
    ) -> None:
        if linear_steps <= 0:
            raise ValueError("The linear step size for bucketing must be positive!")
        if max_linear_value is not None and exponential_multiplier <= 1:
            raise ValueError("The exponential step size for bucketing must be > 1!")
        self._max_linear_value = (
            round_up_to(max_linear_value, linear_steps)
            if max_linear_value is not None
            else None
        )
        self.linear_steps = linear_steps
        self.exponential_multiplier = exponential_multiplier

    @cached_property
    def _first_exponential_bucket(self) -> int:
        """The index of the first bucket that uses exponential, rather than linear, sizes."""

        return int(assert_not_none(self._max_linear_value) / self.linear_steps) + 1

    @cached_property
    def _log_max_linear_value(self) -> float:
        """Log of the max linear value."""

        return math.log(assert_not_none(self._max_linear_value))

    def bucket(self, value: float) -> int:
        """Given a value to be added to the histogram, figure out which bucket it goes in."""
        # If the value is under the linear cap (C), then the bucket number is floor(v/s)
        if self._max_linear_value is None or value < self._max_linear_value:
            return int(value / self.linear_steps)
        # Beyond C, the value is floor(C/s) + 1 + floor(log(v/C)/K)
        log_beyond_cap = math.log(value) - self._log_max_linear_value
        bucket_beyond_cap = int(log_beyond_cap / self.exponential_multiplier)
        return self._first_exponential_bucket + bucket_beyond_cap

    def bucket_width(self, bucket: int) -> float:
        """Find the width (in the histogram's natural units) of a given bucket."""

        if self._max_linear_value is None or bucket < self._first_exponential_bucket:
            return self.linear_steps
        shifted = bucket - self._first_exponential_bucket + 1
        return math.pow(self.exponential_multiplier, shifted)

    def value_for_bucket(self, bucket: int) -> float:
        """Return the (min) value for the indicated bucket."""

        if self._max_linear_value is None or bucket < self._first_exponential_bucket:
            return self.linear_steps * bucket
        shifted = bucket - self._first_exponential_bucket + 1
        return self._max_linear_value * math.pow(self.exponential_multiplier, shifted)

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, Bucketing)
            and other._max_linear_value == self._max_linear_value
            and other.linear_steps == self.linear_steps
            and other.exponential_multiplier == self.exponential_multiplier
        )


DEFAULT_BUCKETING = Bucketing()
