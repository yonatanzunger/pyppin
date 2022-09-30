"""Useful tools for working with iterators and iterables."""

import math
import random
from collections import defaultdict
from typing import Callable, Dict, Iterable, List, TypeVar

DataType = TypeVar("DataType")
KeyType = TypeVar("KeyType")


def split(
    source: Iterable[DataType], key: Callable[[DataType], KeyType]
) -> Dict[KeyType, List[DataType]]:
    """Split a source according to keys, like a SQL GROUP BY statement.

    For each value in ``source``, call key(value), and return a dict whose keys are all possible
    keys, and whose values are a list of all values in the original source who had that key.
    """
    result: Dict[KeyType, List[DataType]] = defaultdict(list)
    for value in source:
        result[key(value)].append(value)
    return result


def sample(source: Iterable[DataType], count: int) -> List[DataType]:
    """Select <count> randomly sampled items from the stream <source>.

    This function implements `reservoir sampling
    <https://en.wikipedia.org/wiki/Reservoir_sampling>`_ using Li's "Algorithm L."

    Args:
        source: The data from which to sample.
        count: The number of items to select from this sample.

    Returns:
        A list of (up to) [count] items from the source, randomly selected with equal weights.
    """
    assert count >= 0
    if not count:
        return []

    it = iter(source)
    result: List[DataType] = []

    try:
        for k in range(count):
            result.append(next(it))

        w = 1.0

        while True:
            w *= math.pow(random.random(), 1 / count)
            skip = math.floor(math.log(random.random(), 1 - w)) + 1
            for k in range(skip):
                value = next(it)
            result[random.randrange(count)] = value

    except StopIteration:
        return result


# TODO: Weighted reservoir sampling
