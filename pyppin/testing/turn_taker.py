"""A tool to simplify unittesting operations that involve many threads."""

import threading
from typing import Optional, Set, Type, Union


class TurnTaker(object):
    """A tool to manage "turn taking" in multithreaded unittests.

    Testing code where you want to verify that actors in multiple threads interact with a shared
    system in an expected way can be hard. Black-box testing ("the right outcome happened") can
    miss subtle race conditions that only happen sometimes, but white-box testing ("the system
    worked the way my mental model does") is tricky. This class is designed to make that easier.

    Imagine that the threads of your unittest are playing a game with a ball. If one thread wants
    another thread to do something, they ask that thread to do it, and then pass them the ball. When
    that thread is done, they pass the ball back to the first player. Catching the ball lets the
    first player know that the thing should now be done, and they can check what's going on in the
    world. By passing the ball back and forth, all the threads can take turns doing things.

    The easiest way to illustrate how it works is with an example::

        def testSomething(self) -> None:
            class Player1(TurnTaker):
                def run(self) -> None:
                    # This thread will go first. It does some initial prep work, then
                    self.pass_and_wait('Player2')

                    # Now it waits until player2 passes back to it, and it does some other things.

                    # Finally, it passes back to player2 and doesn't wait for anything else.
                    self.pass_and_finish('Player2')

            class Player2(TurnTaker):
                def run(self) -> None:
                    # This thread will wait until it gets passed the ball by player 1, then
                    # does some initial stuff, and passes back to player 1.

                    self.pass_and_wait('Player1')

                    # Player 1 will finish up and then pass back to us. We wrap up and don't need
                    # to pass to anyone else; when we finish, nobody else is waiting!

            # The unittest then runs the game as follows:
            TestTaker.play(Player1, Player2, first_player=Player1)

    The call to ``play`` starts up threads for both players, but Player 2 doesn't actually start yet
    -- only the first player gets to execute. They do some work and then ``pass_and_wait()`` to
    player 2. This blocks player 1 and unblocks player 2, who now does some other stuff and then
    calls ``pass_and_wait()`` to send control back to player 1. Player 1 does some final checking
    and then calls ``pass_and_finish()``, signalling that it isn't waiting for the ball to show up
    anymore. Since nobody is waiting for any more balls, the game ends, and the unittest has passed!

    Importantly, any exceptions (including assertion failures) raised by one of the players will be
    raised by the call to ``play()``. This is important, because Python doesn't usually propagate
    exceptions across threads; this way, all your players can make assertions in the ordinary
    unittest style and know that they'll lead to test failures in the usual way, too.

    You can find several examples of how to use this in `pyppin's own unittests
    <https://github.com/yonatanzunger/pyppin/tree/master/tests/threading>`_.)
    """

    class PlayerExitedWithoutPassing(Exception):
        """Raised if a player exited without passing, while other players were waiting.

        This usually means a bug in your unittest!
        """

    class PlayerActedWhenNotTheirTurn(Exception):
        """Raised if a player acts when it isn't their turn."""

    def __init__(self, game: "_Game") -> None:
        # You never directly instantiate a TurnTaker.
        self._game = game

    def run(self) -> None:
        """The basic method which subclasses implement: Actually do this thread's job in the test!

        This method will be called during this player's first turn, and can control the flow of
        the game by calling various instance methods.
        """
        raise NotImplementedError()

    def pass_and_wait(self, to: Union[str, Type["TurnTaker"]]) -> None:
        """Pass the ball to another player and wait for my next turn."""
        self._game.pass_to(self, to, wait=True)

    def pass_and_finish(self, to: Union[str, Type["TurnTaker"]]) -> None:
        """Pass the ball to another player and don't wait for your next turn; you're done.

        Every player, except the last one, must call this immediately before returning from their
        run method.
        """
        self._game.pass_to(self, to, wait=False)

    def pass_without_waiting(self, to: Union[str, Type["TurnTaker"]]) -> None:
        """Pass the ball *without* waiting, but not necessarily finishing my function.

        If you call this, you had better call wait_for_my_turn() before trying to do anything
        else with the ball! This function is primarily useful when you need to start a blocking
        operation, like trying to grab a mutex that you know won't be available until another
        player does something.
        """
        self._game.pass_to(self, to, wait=False)

    def wait_for_my_turn(self) -> None:
        """Block until it's my next turn.

        You usually don't need to call this explicitly, unless you called pass_without_waiting.
        A player's run method isn't called until their first turn, and pass_and_wait calls this
        internally.
        """
        self._game.wait_for_turn(self)

    @staticmethod
    def play(
        *players: Type["TurnTaker"],
        first_player: Optional[Union[str, Type["TurnTaker"]]] = None,
        final_timeout: Optional[float] = 5,
    ) -> None:
        """The main function you call to play a game.

        Args:
            players: The set of player classes that you want to play. During the game, you
                can refer to any player by the name of the class.
            first_player: Who goes first. If not given, the first player in the list does.
            final_timeout: How long, in seconds, to wait for the game to finish before erroring
                out.

        Raises:
            KeyError: If first_player is not one of the players.
            TurnTaker.PlayerExitedWithoutPassing: If some player returned from their run method
                without passing while other players were still waiting.
            TurnTaker.PlayerActedWhenNotTheirTurn: What it says on the tin.
            TimeoutError: If final_timeout expires while there are active threads.
            Any other exception: If raised by the players themselves!
        """
        if isinstance(first_player, type):
            first_player = first_player.__name__
        elif first_player is None:
            first_player = players[0].__name__

        _Game(*players).play(first_player, timeout=final_timeout)

    @property
    def name(self) -> str:
        """Return the name of the player, which is the same as the name of the class."""
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
        self.error: Optional[Exception] = None

    ###########################################################################################
    # Functions which are called by TurnTakers. These functions may raise exceptions like ordinary
    # functions.

    def name(self, player: Union[str, TurnTaker, Type[TurnTaker]]) -> str:
        if isinstance(player, type):
            return player.__name__
        elif isinstance(player, TurnTaker):
            return player.name
        else:
            return player

    def wait_for_turn_locked(
        self, player: Union[str, TurnTaker, Type[TurnTaker]]
    ) -> None:
        """Block until it is player's turn. Requires that self.lock be held."""
        player = self.name(player)
        self.waiters.add(player)
        self.cond.wait_for(lambda: self.error or self.active_player == player)
        self.waiters.remove(player)

        # This will stop any active players, but it won't generate any extra exceptions or errors
        # because we'll silently absorb it.
        if self.error:
            raise _AlreadyAborted()

    def wait_for_turn(self, player: Union[str, TurnTaker, Type[TurnTaker]]) -> None:
        with self.lock:
            self.wait_for_turn_locked(player)

    def pass_to(
        self,
        from_: Union[str, TurnTaker, Type[TurnTaker]],
        to: Union[str, TurnTaker, Type[TurnTaker]],
        wait: bool,
    ) -> None:
        """Pass to another player, and optionally wait for from_'s next turn."""
        from_ = self.name(from_)
        to = self.name(to)
        with self.lock:
            if self.active_player != from_:
                raise TurnTaker.PlayerActedWhenNotTheirTurn(
                    f"{from_} tried to pass to {to} but isn't the active player!"
                )

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

        if not self.error:
            try:
                player.run()

                # When the player finishes, either it should have passed the ball to someone
                # else, or it should be the last player standing.
                with self.lock:
                    # This shouldn't be able to happen, but just in case.
                    if player.name in self.waiters:
                        raise RuntimeError(
                            f"Player {player.name} exited while waiting for their turn!"
                        )

                    if self.active_player == player.name and self.waiters:
                        # This means that the player ended their execution without passing.
                        # If they're the last player remaining, this is great! If not, it is
                        # not great.
                        raise TurnTaker.PlayerExitedWithoutPassing(
                            f"Player {player.name} finished execution without passing while "
                            f"other players ({', '.join(sorted(self.waiters))}) were still "
                            "waiting!"
                        )

            except _AlreadyAborted:
                pass
            except Exception as e:
                with self.lock:
                    self.error = e

        abort = False
        with self.lock:
            if self.error:
                # If we have errors, wake everyone up so we can stop all the waiters.
                self.cond.notify_all()
                abort = True

        if abort:
            barrier.abort()
        else:
            try:
                barrier.wait()
            except threading.BrokenBarrierError:
                pass

    def play(self, first_player: str, timeout: Optional[float]) -> None:
        """The main loop of play!"""
        if first_player not in self.players:
            raise KeyError(
                f"The first player '{first_player}' is not in the list of known players!"
            )

        barrier = threading.Barrier(len(self.players) + 1)
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
            barrier.wait(timeout=timeout)
        except threading.BrokenBarrierError:
            pass
        else:
            # Rather confusingly, returning from wait in a broken state but *without* raising
            # BrokenBarrierError is how the barrier indicates a timeout.
            if barrier.broken:
                raise TimeoutError()

        if self.error:
            raise self.error

        for thread in threads:
            thread.join()
