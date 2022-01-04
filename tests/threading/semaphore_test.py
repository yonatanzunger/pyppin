import unittest


class SemaphoreTest(unittest.TestCase):
    pass


# Simple test: thread 1 acquires, thread 2 requests and blocks, thread 1 releases, thread 2
# unblocks. Do this with threads appending to a vector when they unblock.

# Fancier test: thread 1 starts, thread 2 starts, thread 3 stops, thread 4 tries to start, thread 1
# exits, thread 2 exits, thread 3 finishes. This will require a ball-passer.
