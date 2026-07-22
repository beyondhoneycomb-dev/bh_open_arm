"""The collision guard — a detection-only, fail-closed latch source (`WP-1-03`).

`12` FR-SAF-074 fixes the architecture, and it is deliberately not "the guard stops
the arm". The guard only *detects*; enforcement is the single `send_action` gateway,
which holds the latch this guard sets. Concretely:

- **Detection only.** The guard never writes the bus. When it decides to stop, it
  calls back to engage the scheduler's safety latch and returns — the hold frame is
  emitted by the scheduler tick, not by the guard (`12` FR-SAF-074 ③).
- **Fail-closed.** A missing observation, a failed bus read, or a lock timeout is
  not "no news is good news": each latches immediately, because a guard that cannot
  see is a guard that must assume the worst (`12` FR-SAF-074 ②, acceptance ⑩).
- **Shared lock, paused in bus-exclusive sections.** The guard and the control path
  share one CAN lock. During a bus-exclusive section — torque enable, mode set — the
  control side `pause()`s the guard so its read neither contends for the bus nor
  reads a torn state and latches on it (`12` FR-SAF-074 ④, acceptance ⑪).
- **Latched until operator ack, with the cause recorded.** The latch it sets is the
  one-way `SafetyLatch`: nothing in the tick path clears it, only an operator ack,
  and the cause is carried in the `LatchReason` (`12` FR-SAF-074 ⑤, acceptance ⑫).

An actual collision (a joint-torque residual over threshold) latches too, but only
after a configurable number of consecutive over-threshold polls (debounce); the
fail-closed conditions do not debounce, because a blind guard has no reason to wait.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from backend.actuation.clock import Clock
from ops.cancel.scheduler import LatchReason

# Default consecutive over-threshold polls before a residual-based collision latches.
# The blind (fail-closed) conditions ignore this — only a real-residual detection
# debounces, so a single noisy sample does not stop the arm.
DEFAULT_COLLISION_DEBOUNCE = 3


class GuardCause(Enum):
    """Why the guard latched — a distinct cause per fail-closed condition (acceptance ⑩)."""

    OBSERVATION_MISSING = "observation_missing"
    BUS_READ_FAILED = "bus_read_failed"
    LOCK_TIMEOUT = "lock_timeout"
    COLLISION_RESIDUAL = "collision_residual"


@dataclass(frozen=True)
class GuardSample:
    """One detection poll's inputs, as the detection thread observes them.

    Attributes:
        observation_present: Whether an observation frame arrived this poll.
        bus_read_ok: Whether the bus read for this poll succeeded.
        lock_acquired: Whether the shared CAN lock was acquired within its timeout.
        residual_exceeded: Whether a joint-torque residual crossed the collision
            threshold this poll.
    """

    observation_present: bool
    bus_read_ok: bool
    lock_acquired: bool
    residual_exceeded: bool

    @staticmethod
    def healthy() -> GuardSample:
        """A poll with everything nominal — no latch.

        Returns:
            (GuardSample) A sample that latches nothing.
        """
        return GuardSample(
            observation_present=True,
            bus_read_ok=True,
            lock_acquired=True,
            residual_exceeded=False,
        )


@dataclass(frozen=True)
class GuardVerdict:
    """The guard's decision for one poll.

    Attributes:
        latched: Whether this poll latched.
        cause: The distinct cause when latched, else None.
    """

    latched: bool
    cause: GuardCause | None


_SAFE = GuardVerdict(latched=False, cause=None)


class CollisionGuard:
    """A detection-only guard that sets — but never itself enforces — a safety latch.

    Ownership: holds the callback that engages the scheduler's latch, a clock for
    latch timestamps, and its own paused/consecutive-poll state. It holds no CAN
    handle and no writer — it cannot touch the bus, which is the structural half of
    "the guard never writes the bus" (`12` FR-SAF-074 ③).
    """

    def __init__(
        self,
        on_latch: Callable[[LatchReason], None],
        clock: Clock,
        collision_debounce: int = DEFAULT_COLLISION_DEBOUNCE,
    ) -> None:
        """Wire the guard to its latch callback and clock.

        Args:
            on_latch: Engages the scheduler's safety latch with the cause; the guard
                calls this instead of writing the bus.
            clock: Time source for the latch timestamp.
            collision_debounce: Consecutive over-threshold polls before a residual
                collision latches. Fail-closed conditions ignore this.
        """
        self._on_latch = on_latch
        self._clock = clock
        self._collision_debounce = collision_debounce
        self._paused = False
        self._consecutive_residual = 0
        self._latched = False

    @property
    def is_paused(self) -> bool:
        """Whether the guard is currently paused for a bus-exclusive section."""
        return self._paused

    @property
    def is_latched(self) -> bool:
        """Whether the guard has latched (until an operator ack clears the scheduler)."""
        return self._latched

    def pause(self) -> None:
        """Enter a bus-exclusive section: suspend detection to avoid a false latch.

        While paused the guard reads nothing and latches nothing — a torn read during
        a torque-enable or mode-set is expected, not a collision (`12` FR-SAF-074 ④).
        """
        self._paused = True

    def resume(self) -> None:
        """Leave a bus-exclusive section: resume detection.

        The consecutive-residual counter is reset so a stale count from before the
        pause cannot combine with post-resume polls into a spurious latch.
        """
        self._paused = False
        self._consecutive_residual = 0

    def poll(self, sample: GuardSample) -> GuardVerdict:
        """Evaluate one detection poll, latching fail-closed on a blind condition.

        Args:
            sample: The poll's observation/bus/lock/residual state.

        Returns:
            (GuardVerdict) Whether this poll latched, and the distinct cause.
        """
        if self._paused:
            return _SAFE

        cause = self._fail_closed_cause(sample)
        if cause is not None:
            return self._latch(cause)

        if sample.residual_exceeded:
            self._consecutive_residual += 1
            if self._consecutive_residual >= self._collision_debounce:
                return self._latch(GuardCause.COLLISION_RESIDUAL)
        else:
            self._consecutive_residual = 0
        return _SAFE

    def _fail_closed_cause(self, sample: GuardSample) -> GuardCause | None:
        """Return the fail-closed cause for a blind poll, or None when the guard can see."""
        if not sample.observation_present:
            return GuardCause.OBSERVATION_MISSING
        if not sample.bus_read_ok:
            return GuardCause.BUS_READ_FAILED
        if not sample.lock_acquired:
            return GuardCause.LOCK_TIMEOUT
        return None

    def _latch(self, cause: GuardCause) -> GuardVerdict:
        """Engage the latch through the callback and record the cause."""
        self._latched = True
        self._on_latch(
            LatchReason(
                gate_id=f"COLLISION_GUARD:{cause.value}",
                previous_state="PASS",
                new_state="LATCHED",
                latched_at=self._clock.now(),
            )
        )
        return GuardVerdict(latched=True, cause=cause)
