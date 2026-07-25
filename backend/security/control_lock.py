"""The two-level control lock: device-level CAN fd (L1) + command source (L2).

`FR-OPS-074`/`FR-OPS-075` require control authority to be held at **two independent
levels**, because either alone is insufficient:

- **L1 — device level.** Exactly one process owns the CAN file descriptor. This is
  the Wave-0B `flock` lock (`backend.can.lock.LockManager`), reused here, not
  rebuilt. It stops a second *process* from opening the bus.
- **L2 — command-source level.** Exactly one of {VR, GUI, policy} may command at a
  time. `FR-OPS-075` is explicit that L1 alone cannot prevent two controllers being
  active *inside one process* — two command sources both driving the single CAN
  writer. L2 is that second, independent gate, and it is what this module adds.

`TwoLevelControlLock` composes the two so a caller reads both, but keeps them
separable: each is enforced on its own (`CG-5-08g`), and neither substitutes for the
other. Only the operator may hold L2; an observer holds neither (`FR-OPS-077`), and
admin holds force-release authority but is not a command source.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.actuation.clock import Clock
from backend.can.lock.manager import AcquireResult, LockManager
from contracts.ws import CONTROL_HOLDER_ROLE, WsRole


class CommandSource(Enum):
    """The command sources at L2 — exactly one may hold command authority (`FR-OPS-075`)."""

    VR = "vr"
    GUI = "gui"
    POLICY = "policy"


@dataclass(frozen=True)
class CommandLockHolder:
    """The current L2 command-source lock holder.

    Attributes:
        session_id: The holding control session.
        source: Which command source it is (VR/GUI/policy).
        acquired_at: Server-clock time the lock was taken, seconds — the queryable
            acquisition time (`FR-OPS-074`).
    """

    session_id: str
    source: CommandSource
    acquired_at: float


class L2Refusal(Enum):
    """Why an L2 acquisition was refused — one reason each (`FR-OPS-074`/`FR-OPS-077`)."""

    # Only the operator role may hold command authority; observer/admin may not.
    NOT_OPERATOR = "not_operator"
    # Another session already holds the single command-source lock.
    ALREADY_HELD = "already_held"


@dataclass(frozen=True)
class L2AcquireOutcome:
    """The outcome of an L2 acquisition attempt.

    Attributes:
        granted: True when this call now holds the command-source lock.
        holder: The current holder after the call — the acquirer on success, the
            incumbent on an `ALREADY_HELD` refusal, or None if refused for role.
        refusal: The single reason, or None on success.
    """

    granted: bool
    holder: CommandLockHolder | None
    refusal: L2Refusal | None


class CommandSourceLock:
    """L2: a single-holder command-source lock, independent of the device (L1) lock.

    Ownership/threading: one instance guards one robot's command authority. It holds
    a single optional holder and is not shared across threads without external
    synchronisation. It opens no file and no socket — it is the *command-source*
    level, deliberately separate from L1's filesystem `flock`.
    """

    def __init__(self, clock: Clock) -> None:
        """Create an unheld command-source lock.

        Args:
            clock: The server monotonic clock, stamped onto the holder record.
        """
        self._clock = clock
        self._holder: CommandLockHolder | None = None

    @property
    def holder(self) -> CommandLockHolder | None:
        """The current command-source lock holder, or None when unheld.

        Returns:
            (CommandLockHolder | None) The holder record for `FR-OPS-074` queries.
        """
        return self._holder

    def is_held_by(self, session_id: str) -> bool:
        """Report whether a given session currently holds L2.

        Args:
            session_id: The session to check.

        Returns:
            (bool) True when that session is the current holder.
        """
        return self._holder is not None and self._holder.session_id == session_id

    def acquire(self, session_id: str, source: CommandSource, role: WsRole) -> L2AcquireOutcome:
        """Take the command-source lock for one session, or refuse.

        Only the operator role may hold command authority; a re-acquire by the current
        holder is idempotent; any other contender is refused while the lock is held.

        Args:
            session_id: The acquiring session.
            source: The command source it commands as (VR/GUI/policy).
            role: The acquirer's WS role.

        Returns:
            (L2AcquireOutcome) Granted with the new holder, or a refusal with the
            incumbent (if any).
        """
        if role is not CONTROL_HOLDER_ROLE:
            return L2AcquireOutcome(granted=False, holder=None, refusal=L2Refusal.NOT_OPERATOR)
        if self._holder is not None and self._holder.session_id != session_id:
            return L2AcquireOutcome(
                granted=False, holder=self._holder, refusal=L2Refusal.ALREADY_HELD
            )
        self._holder = CommandLockHolder(
            session_id=session_id, source=source, acquired_at=self._clock.now()
        )
        return L2AcquireOutcome(granted=True, holder=self._holder, refusal=None)

    def release(self) -> None:
        """Release the command-source lock. Safe to call when unheld."""
        self._holder = None


class TwoLevelControlLock:
    """Composes L1 (device CAN fd) and L2 (command source), each enforced independently.

    Ownership: holds the reused Wave-0B `LockManager` (L1) and the `CommandSourceLock`
    (L2). It exposes both rather than merging them, because `FR-OPS-075`'s whole point
    is that they are two gates: L1 refuses a second *process* the bus; L2 refuses a
    second *command source* inside one process. A merge would hide that a caller
    holding L1 can still be blocked at L2 (`CG-5-08g`).
    """

    def __init__(self, lock_manager: LockManager, command_lock: CommandSourceLock) -> None:
        """Compose the two levels from their reused/added owners.

        Args:
            lock_manager: The Wave-0B CAN-fd lock manager (L1).
            command_lock: The command-source lock (L2).
        """
        self._lock_manager = lock_manager
        self._command_lock = command_lock

    @property
    def device_lock(self) -> LockManager:
        """The L1 device-level CAN-fd lock manager.

        Returns:
            (LockManager) The reused Wave-0B lock manager.
        """
        return self._lock_manager

    @property
    def command_lock(self) -> CommandSourceLock:
        """The L2 command-source lock.

        Returns:
            (CommandSourceLock) The single-command-source lock.
        """
        return self._command_lock

    def acquire_device(self, ifaces: tuple[str, ...]) -> AcquireResult:
        """Acquire the L1 device lock for a set of CAN interfaces (all-or-nothing).

        Args:
            ifaces: CAN interfaces to lock.

        Returns:
            (AcquireResult) The Wave-0B acquisition result.
        """
        return self._lock_manager.acquire_all(ifaces)

    def acquire_command_source(
        self, session_id: str, source: CommandSource, role: WsRole
    ) -> L2AcquireOutcome:
        """Acquire the L2 command-source lock — independent of whether L1 is held.

        Args:
            session_id: The acquiring session.
            source: The command source (VR/GUI/policy).
            role: The acquirer's WS role.

        Returns:
            (L2AcquireOutcome) The L2 outcome; L2 refuses a second source even when
            L1 is held by this very process (the `FR-OPS-075` point).
        """
        return self._command_lock.acquire(session_id, source, role)
