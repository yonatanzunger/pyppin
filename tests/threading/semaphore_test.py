import threading
import unittest
from typing import List

from pyppin.testing.turn_taker import TurnTaker
from pyppin.threading.semaphore import Semaphore


class SemaphoreTest(unittest.TestCase):
    # Use a different name for "self" because we have nested classes.
    def testSimpleOrderOfOperations(test) -> None:
        # In this test, we'll have two worker threads, and a semaphore of capacity 1, which is
        # basically just a Dijkstra mutex.

        ops: List[str] = []
        sem = Semaphore(1)

        class Thread1(TurnTaker):
            def run(self) -> None:
                with sem:
                    ops.append("Thread 1 acquired the lock")
                    self.pass_and_wait("Thread2")
                ops.append("Thread 1 released the lock")
                self.pass_and_finish("Thread2")

        class Thread2(TurnTaker):
            def run(self) -> None:
                test.assertFalse(sem.try_acquire(1))
                ops.append("Thread 2 failed to acquire")
                self.pass_and_wait("Thread1")
                with sem.get() as resource:
                    ops.append("Thread 2 acquired the lock")
                    test.assertEqual(Semaphore.AcquireResult.SUCCESS, resource.status)
                    test.assertTrue(resource)
                    test.assertEqual(1, resource.amount)
                ops.append("Thread 2 released the lock")

        TurnTaker.play(Thread1, Thread2)

        test.assertEqual(
            [
                "Thread 1 acquired the lock",
                "Thread 2 failed to acquire",
                "Thread 1 released the lock",
                "Thread 2 acquired the lock",
                "Thread 2 released the lock",
            ],
            ops,
        )

    def testBlockOnSemaphore(test) -> None:
        ops: List[str] = []
        sem = Semaphore(1)
        pause = threading.Event()

        class Thread1(TurnTaker):
            def run(self) -> None:
                with sem:
                    ops.append("Thread 1 acquired one unit")
                    test.assertEqual(Semaphore.Status(1, 1, False), sem.status)
                    self.pass_and_wait("Thread2")
                    ops.append("It became thread 1's turn")

                ops.append("Thread 1 released one unit")
                # Pause *before* we pass the turn over.
                pause.wait()
                self.pass_and_finish("Thread2")

        class Thread2(TurnTaker):
            def run(self) -> None:
                # When thread 2 is first called, thread 1 should hold one unit, so our acquire
                # should block.
                test.assertFalse(sem.try_acquire(1))
                ops.append("Thread 2 failed to acquire")

                # Now we're going to pass back to thread 1, and have ourselves block in the interim.
                self.pass_without_waiting("Thread1")
                with sem:
                    ops.append("Thread 2 acquired one unit")
                    pause.set()

                    self.wait_for_my_turn()
                    ops.append("It became thread 2's turn")
                    test.assertEqual(Semaphore.Status(1, 1, False), sem.status)

                ops.append("Thread 2 released one unit")

        TurnTaker.play(Thread1, Thread2)

        test.assertEqual(
            [
                "Thread 1 acquired one unit",
                "Thread 2 failed to acquire",
                "It became thread 1's turn",
                "Thread 1 released one unit",
                "Thread 2 acquired one unit",  # On thread 1's turn!
                "It became thread 2's turn",
                "Thread 2 released one unit",
            ],
            ops,
        )

    def testShutDownSemaphore(test) -> None:
        ops: List[str] = []
        sem = Semaphore(1)

        class Thread1(TurnTaker):
            def run(self) -> None:
                with sem:
                    ops.append("Thread 1 acquired one unit")
                    test.assertEqual(Semaphore.Status(1, 1, False), sem.status)
                    self.pass_and_wait("Thread2")
                    ops.append("It became thread 1's turn")

                ops.append("Thread 1 released one unit")
                self.pass_and_finish("Thread3")

        class Thread2(TurnTaker):
            def run(self) -> None:
                # When thread 2 is first called, thread 1 should hold one unit, so our acquire
                # should block.
                test.assertFalse(sem.try_acquire(1))
                ops.append("Thread 2 failed to acquire")

                # Now we're going to pass over to thread *3* while we block.
                self.pass_without_waiting("Thread3")
                with test.assertRaises(BrokenPipeError):
                    sem.acquire_checked(1)

                ops.append("Thread 2 acquire interrupted")
                # We don't need to wait for anything else, we're done here.

        class Thread3(TurnTaker):
            def run(self) -> None:
                ops.append("Thread 3 stops the semaphore")
                self.pass_without_waiting("Thread1")
                sem.stop()
                ops.append("The semaphore has stopped")
                test.assertEqual(Semaphore.Status(1, 0, True), sem.status)

        TurnTaker.play(Thread1, Thread2, Thread3)

        # We expect ops to be seq1, then any intermingling of seq2 and seq3, then seq4.
        expectation = [
            # These three should come first
            "Thread 1 acquired one unit",  # 0
            "Thread 2 failed to acquire",  # 1
            "Thread 3 stops the semaphore",  # 2
            # Then the next three, with the fourth one ("Thread 2...") intermingled in
            # arbitrary order relative to them.
            # i.e. sequence 3 4 5 6, 3 4 6 5, 3 6 4 5, 6 3 4 5.
            "It became thread 1's turn",
            "Thread 1 released one unit",
            "The semaphore has stopped",
            "Thread 2 acquire interrupted",
            # And finally this one
        ]
        indices = [expectation.index(text) for text in ops]
        if not (
            indices == [0, 1, 2, 3, 4, 5, 6]
            or indices == [0, 1, 2, 3, 4, 6, 5]
            or indices == [0, 1, 2, 3, 6, 4, 5]
            or indices == [0, 1, 2, 6, 3, 4, 5]
        ):
            indented = "\n".join(["  " + line for line in ops])
            print(indices)
            raise AssertionError("Got operations in an unexpected order:\n" + indented)


# Simple test: thread 1 acquires, thread 2 requests and blocks, thread 1 releases, thread 2
# unblocks. Do this with threads appending to a vector when they unblock.

# Fancier test: thread 1 starts, thread 2 starts, thread 3 stops, thread 4 tries to start, thread 1
# exits, thread 2 exits, thread 3 finishes. This will require a ball-passer.
