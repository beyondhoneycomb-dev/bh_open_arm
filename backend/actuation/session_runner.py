"""The thread that calls the arm session's tick, at a period the kernel holds.

`ArmSession.tick` is data-in, decision-out and blocks on nothing but the read. Something has to
call it, and a session with no caller is the same defect one level up: the board stays empty, the
deadman is never polled, and a lease that lapsed latches nothing.

The period is a `TickPacer` rather than a sleep after the work, for the reason that module states
in full: `sleep(period)` after a tick makes the real interval `work + period`, and `work` is the
term that moves. Here that shows up as a board whose readings are spaced by however long the bus
took, and as a deadman poll whose rate drifts with it — the two things a control period exists to
pin. The pacer also counts the deadlines it missed, so a loop that ran late says so.

Ownership and threading: one runner drives one session, and it is the only thread that calls
`tick`. That is what the board's lock-free publish rests on — a single writer — so a second runner
over one session would put the tearing back. It borrows the session and owns nothing but its
thread and its timer.

A tick that raises stops the loop and the exception is kept. `HoldMaintainer` makes the same
choice for the same reason: a maintenance loop that died quietly is worse than one that stopped
loudly, because the board it fed keeps answering with its last frame and only a reader checking
the age would ever notice.

Loudly means at the moment of death, not at shutdown. Keeping the exception in an attribute is
not reporting it: the one reader of `failure` runs after the server's own loop has returned, so a
reader lost to a vanished CAN adapter stayed invisible for as long as the operator left the
window open — measured once at 45 minutes, with the browser's badge reporting a connected arm the
whole time. The write to stderr here is what makes the process say so while it is still up; the
telemetry frame's `stale` field is what makes the browser say so.
"""

from __future__ import annotations

import sys
import threading

from backend.actuation.pacer import PacerError, TickPacer
from backend.actuation.session import ArmSession

SECONDS_PER_HZ = 1.0

# How long `stop` waits for the loop to leave. One tick is the expected wait, because the pacer
# blocks in `read()` and a set flag is seen when that read returns; this is the bound for a tick
# whose read is itself stuck.
RUNNER_STOP_JOIN_TIMEOUT_SEC = 2.0


class ArmSessionRunner(threading.Thread):
    """Calls `ArmSession.tick` on a kernel-held period until stopped."""

    def __init__(self, session: ArmSession, tick_hz: float) -> None:
        """Bind the runner to the session it drives and the rate it drives it at.

        The rate is checked here rather than at the first `wait`, because the timer is armed on
        the thread and a refusal raised there would surface as a runner that started and never
        ticked.

        Args:
            session: The arm session whose tick this calls. Borrowed, not owned.
            tick_hz: Ticks per second; must be above zero.

        Raises:
            ValueError: If the rate is not above zero. A zero period arms a one-shot timer, so
                the loop would block forever on its second wait rather than run fast.
        """
        super().__init__(name="oa-arm-session", daemon=True)
        if tick_hz <= 0.0:
            raise ValueError(f"tick rate must be above zero, got {tick_hz}")
        self._session = session
        self._period_sec = SECONDS_PER_HZ / tick_hz
        # Not `_stop`: `threading.Thread._stop` is a method the thread's own bootstrap calls when
        # `run` returns, and shadowing it with an Event makes the thread raise on its way out.
        self._stop_event = threading.Event()
        self.failure: BaseException | None = None
        self.ticks = 0
        self.overruns = 0

    def run(self) -> None:
        """Tick until stopped, keeping whatever ended the loop."""
        try:
            pacer = TickPacer(self._period_sec)
        except (ValueError, PacerError) as unavailable:
            self.failure = unavailable
            return
        try:
            while not self._stop_event.is_set():
                try:
                    self._session.tick()
                except BaseException as failure:  # noqa: BLE001 — a dead loop is the finding
                    self.failure = failure
                    print(
                        f"the arm session tick died after {self.ticks} ticks: {failure!r}; "
                        "the boards will not advance again until this process restarts.",
                        file=sys.stderr,
                        flush=True,
                    )
                    return
                self.ticks += 1
                pacer.wait()
                self.overruns = pacer.overruns
        finally:
            pacer.close()

    def stop(self) -> bool:
        """Stop ticking, waiting a bounded time for the loop to leave.

        Tolerant of never having started, because a server whose startup failed part-way still
        runs its shutdown path and must not raise there.

        The stop is seen up to one period late: a blocked `read()` on the timer is not
        interruptible the way an `Event.wait` was. Nothing here is on the bus, so a late tick
        costs a reading nobody asked for.

        Returns:
            (bool) Whether the loop actually stopped. False means a tick is still running and the
            caller must say so rather than report a clean shutdown.
        """
        self._stop_event.set()
        if self.ident is None:
            return True
        self.join(timeout=RUNNER_STOP_JOIN_TIMEOUT_SEC)
        return not self.is_alive()


__all__ = ["RUNNER_STOP_JOIN_TIMEOUT_SEC", "ArmSessionRunner"]
