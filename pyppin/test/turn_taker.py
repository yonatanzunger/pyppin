"""A tool to manage "turn taking" in multithreaded unittests."""

import threading
import traceback
from typing import List, Optional, Set, Type, Union


class TurnTaker(object):
    """A tool to manage "turn taking" in multithreaded unittests.

    This class makes it easy to handle multithreaded unittests, where you expect that one thread
    will do X, then another thread will do Y, and so on. It doesn't help you test for unexpected
    races, but it does help you test that expected sequences of behavior -- even complicated ones --
    happen as you want.

    It works by modeling "turn taking" as a game where the players (i.e., the threads) pass each
    other a ball. Only the player currently holding the ball can act; once they're done acting,
    they can pass the ball to someone else and either wait for their next turn or decide they're
    done with their part in the game. Once everyone has decided they're done, the game ends.

    To use this, you make (inside your test case!) some subclasses of ``TurnTaker``, each
    of whose ``run()`` methods actually does the logic of your test. These functions can control
    the flow of the game by calling methods like ``pass_to()`` (to pass to another named player and
    wait for their next turn) or ``game_over()`` to end the game.

    Finally, you call TurnTaker.play_game(), passing it all of your classes and telling it who gets
    the ball first; this will walk through the game until completion, at which point you can do any
    final checks on the outputs they made.
    """

    def __init__(self, game: "_Game") -> None:
        # You never directly instantiate a TurnTaker.
        self._game = game

    def run(self) -> None:
        """The basic method which subclasses implement: Actually do this thread's job in the test!

        This method will be called during this player's first turn, and can control the flow of
        the game by calling various instance methods.
        """
        raise NotImplementedError()

    @staticmethod
    def play(
        *players: Type["TurnTaker"],
        first_player: Union[str, Type["TurnTaker"]],
        final_timeout: Optional[float] = 5,
    ) -> None:
        """The main function you call to play a game.

        Args:
            *players: The set of player classes that you want to play. During the game, you
                can refer to any player by the name of the class.
            first_player: The player who should start with the ball.
            final_timeout: How long, in seconds, to wait for the game to finish before erroring
                out.
        """
        if isinstance(first_player, type):
            first_player = first_player.__name__

        _Game(*players).play(first_player, timeout=final_timeout)

    def pass_and_wait(self, to: Union[str, "TurnTaker"]) -> None:
        """Pass the ball to another player and wait for my next turn."""
        self._game.pass_to(self, to, wait=True)

    def pass_and_finish(self, to: Union[str, "TurnTaker"]) -> None:
        """Pass the ball to another player and don't wait for your next turn; you're done.

        You typically this function immediately before returning from run.
        """
        self._game.pass_to(self, to, wait=False)

    @property
    def name(self) -> str:
        return self.__class__.__name__

    def __str__(self) -> str:
        return self.name


##########################################################################################
# Implementation begins here!


class _AlreadyAborted(Exception):
    """Raised when a game is already aborted."""


class _Game(object):
    """The internal implementation of the actual logic."""

    def __init__(self, *players: Type[TurnTaker]) -> None:
        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)
        self.players = {type_.__name__: type_(self) for type_ in players}
        self.active_player: Optional[str] = None
        self.waiters: Set[str] = set()
        # Propagating errors out of child threads is a messy business, so we instead collect them
        # here.
        self.errors: List[str] = []
        self.error_type: Optional[Type[Exception]] = None

    @property
    def abort(self) -> bool:
        return bool(self.errors)

    ###########################################################################################
    # Functions which are called by TurnTakers. These functions may raise exceptions like ordinary
    # functions.

    def name(self, player: Union[str, "TurnTaker"]) -> str:
        return player.name if isinstance(player, TurnTaker) else player

    def wait_for_turn_locked(self, player: Union[str, "TurnTaker"]) -> None:
        """Block until it is player's turn. Requires that self.lock be held."""
        player = self.name(player)
        self.waiters.add(player)
        self.cond.wait_for(lambda: self.abort or self.active_player == player)
        self.waiters.remove(player)

        # This will stop any active players, but it won't generate any extra exceptions or errors
        # because we'll silently absorb it.
        if self.abort:
            raise _AlreadyAborted()

    def pass_to(
        self,
        from_: Union[str, "TurnTaker"],
        to: Union[str, "TurnTaker"],
        wait: bool,
    ) -> None:
        """Pass to another player, and optionally wait for from_'s next turn."""
        from_ = self.name(from_)
        to = self.name(to)
        with self.lock:
            assert (
                self.active_player == from_
            ), f"{from_} tried to pass to {to} but isn't the active player!"
            assert self.active, f"{from_} tried to pass to {to} after game over!"

            self.active_player = to
            self.cond.notify()
            if wait:
                self.wait_for_turn_locked(from_)

    ###########################################################################################
    # The implementation of play itself, and the thread drivers. player_thread must *not* raise
    # exceptions; it should instead catch them and reroute this over to the error list.

    def player_thread(self, player: TurnTaker, barrier: threading.Barrier) -> None:
        """The inner loop of a single player."""
        # Wait for the player's turn to start.
        with self.lock:
            try:
                self.wait_for_turn_locked(player)
            except _AlreadyAborted:
                pass

        error: Optional[str] = None
        if not self.abort:
            try:
                player.run()
            except _AlreadyAborted:
                pass
            except Exception:
                error = f"Failure in {player}:\n{traceback.format_exc()}"

        # When the player finishes, either it should have passed the ball to someone else, or it
        # should be the last player standing.
        with self.lock:
            if error is not None:
                self.errors.append(error)

            # This shouldn't be able to happen, but just in case.
            if player.name in self.waiters:
                self.errors.append(
                    f"Player {player.name} exited while waiting for their turn!"
                )

            if self.active_player == player.name and self.waiters:
                # This means that the player ended their execution without passing. If they're the
                # last player remaining, this is great! If not, it is not great.
                self.errors.append(
                    f"Player {player.name} finished execution without passing while "
                    f"other players ({', '.join(sorted(self.waiters))}) were still waiting!"
                )

            fail = self.abort
            # If we have errors, wake everyone up so we can stop all the waiters.
            if fail:
                self.cond.notify_all()
                barrier.abort()

        if not fail:
            try:
                barrier.wait()
            except threading.BrokenBarrierError:
                pass

    def play(self, first_player: str, timeout: Optional[float]) -> None:
        """The main loop of play!"""
        assert (
            first_player in self.players
        ), f"The first player '{first_player}' is not in the list of known players!"

        barrier = threading.Barrier(len(self.players) + 1, timeout=timeout)
        threads = [
            threading.Thread(
                target=self.player_thread, name=player.name, args=(player, barrier)
            )
            for player in self.players.values()
        ]
        for thread in threads:
            thread.start()

        # Pass to player one.
        with self.lock:
            self.active_player = first_player
            self.active = True
            self.cond.notify()

        # Wait for all the players to finish.
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            errors = "\n\n".join(self.errors)
            raise AssertionError(f"There were errors: {errors}")

        # Now check that there are no stray waiters.

        for thread in threads:
            thread.join()
