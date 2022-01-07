import unittest
from typing import List

from pyppin.testing.turn_taker import TurnTaker


class TurnTakerTest(unittest.TestCase):
    def testSimpleGame(self) -> None:
        result: List[str] = []

        class Player1(TurnTaker):
            def run(self) -> None:
                # Player 1 will go first. It records that it had a turn, then passes to player 2.
                result.append("player 1 turn 1")
                self.pass_and_wait("Player2")

                # After player 2 has gone, it takes another turn, passes back to player 2, and
                # finishes.
                result.append("player 1 turn 2")
                self.pass_and_finish("Player2")

        class Player2(TurnTaker):
            def run(self) -> None:
                result.append("player 2 turn 1")
                self.pass_and_wait("Player1")

                # On player 2's second turn, it ends the game.
                result.append("player 2 turn 2")

        TurnTaker.play(Player1, Player2)

        self.assertEqual(
            [
                "player 1 turn 1",
                "player 2 turn 1",
                "player 1 turn 2",
                "player 2 turn 2",
            ],
            result,
        )

    def testPlayerForgetsToPass(self) -> None:
        result: List[str] = []

        class Player1(TurnTaker):
            def run(self) -> None:
                result.append("player 1 turn 1")
                # Oops! We don't pass to anyone and player2 is left hanging.

        class Player2(TurnTaker):
            def run(self) -> None:
                result.append("player 2 turn 1")

        with self.assertRaises(
            TurnTaker.PlayerExitedWithoutPassing,
            msg="There were errors: Player Player1 finished execution without passing while "
            "other players (Player2) were still waiting!",
        ):
            TurnTaker.play(Player1, Player2)

    def testPlayerRaisesException(self) -> None:
        # Test that exceptions are correctly propagated out to the unittest.
        class Player1(TurnTaker):
            def run(self) -> None:
                raise ValueError("My hovercraft is full of eels!")

        with self.assertRaises(ValueError):
            TurnTaker.play(Player1)
