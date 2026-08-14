"""The arm one process owns: its latch, its board, its lease, and the tick that feeds them.

Everything this composes already existed and none of it had a caller. `ArmStateBoard` has one
writer by construction and had none; `DeadmanController.poll` names its call contract — *once
per tick* — and nothing ticked; the `SafetyLatch` a GUI stop engages had no owner in the process
that serves the GUI, so a stop reached a latch nobody read. Those are one missing object, not
three missing features, and this is that object.

Ownership: the session owns the one `SafetyLatch` and is itself the `LatchTarget` the deadman
drives, the same arrangement `backend/freedrive/session.py` already uses and for the same
reason — two latches would mean a stop the deadman cannot see and an expiry the operator cannot
clear. It owns the lease the deadman renews. It does not own the arm: each side's read arrives as
a callable, so a host with a bus and a host with a synthetic frame differ in one argument and in
nothing else.

**One latch, one board per side.** The two counts are different on purpose. A stop is a fact
about the rig — `ARM_SIDES` is `("left", "right")` and no operator means "stop the left one" — so
a second latch would be a stop that reached half the machine. A reading is a fact about one arm:
`ArmState` carries the frozen eight-slot layout with no side dimension, and `ArmStateBoard` says
in its own docstring that two followers sharing a process would otherwise judge each other's arm.
So the tick reads every side and publishes each to its own board, all from the one tick, which is
also what keeps two arms' frames comparable.

Threading: one thread calls `tick`, and it is the same thread throughout — the board's lock-free
publish is a single-writer arrangement, and `TickPacer` is explicit that one pacer drives one
loop. Every other caller reads `board.view()`. The latch is engaged from the WebSocket thread and
read from the tick, which is safe on the same terms the latch already relies on: a single
attribute holding either a reason or None.

**This session does not send.** It has no bus handle and no engage sequence, so it publishes what
it read and there is nothing here a command can reach. What follows from that is stated where it
is charged: `backend/ws/arm_channel.py` refuses a `command` frame visibly, because a command
accepted by a process that cannot deliver it is a frame the operator watched leave with nothing
behind it — the failure `NORM-007` names.

The latch is therefore attributable and clearable but stops nothing, and that is the honest state
of this deployment rather than a bug in it: what a stop stops is the loop that commands, and the
loop that commands does not live here yet.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from backend.actuation.board import ArmState, ArmStateBoard
from backend.actuation.clock import Clock
from backend.actuation.guard import GuardSample
from backend.actuation.latch import SafetyLatch
from backend.actuation.lease import LeaseManager
from backend.deadman import DEADMAN_LEASE_DURATION_SEC, DeadmanController
from contracts.units import Deg, Nm
from ops.cancel.scheduler import LatchReason

# One read of the arm: the pose, the torque reported in the same frame, and what that read told
# the collision guard. A tuple rather than a type of its own because it is what
# `OaOpenArmFollower._poll_states` already returns and what `ArmState` already carries — a third
# name between them would be a shape to keep in step with two others.
ArmFrame = tuple[tuple[Deg, ...], tuple[Nm, ...], GuardSample]
ArmReader = Callable[[], ArmFrame]


class ArmSession:
    """One process's arm: the latch every source engages, the board every reader reads."""

    def __init__(
        self,
        clock: Clock,
        read_arms: Mapping[str, ArmReader],
        lease_duration_sec: float = DEADMAN_LEASE_DURATION_SEC,
    ) -> None:
        """Compose the latch, one board per side, the lease and the deadman over one clock.

        Args:
            clock: The monotonic source the boards' ages, the lease's expiry and the latch's
                timestamps are all read from. One clock, so an age here and an expiry there
                cannot disagree.
            read_arms: One read per arm side, each answering pose, torque and guard sample from
                a single read of that arm. Callables rather than an interface because the two
                things that could satisfy an interface today — the CAN-backed follower and the
                dummy robot — do not share a shape, and a seam guessed from one of them fits
                neither.
            lease_duration_sec: The horizon an accepted renewal grants, passed through to the
                deadman so the lease it renews and the lease it judges are one.

        Raises:
            ValueError: If no side was given. A session over no arm would tick, latch and
                publish nothing, which reads from the outside like a healthy idle rig.
        """
        if not read_arms:
            raise ValueError("an arm session needs at least one side to read")
        self._clock = clock
        self._read_arms = dict(read_arms)
        self._latch = SafetyLatch()
        self._boards = {side: ArmStateBoard(clock=clock) for side in self._read_arms}
        self._lease = LeaseManager(lease_duration_sec)
        self._deadman = DeadmanController(
            lease=self._lease,
            latch_target=self,
            clock=clock,
            lease_duration_sec=lease_duration_sec,
        )
        self._tick_index = 0

    @property
    def sides(self) -> tuple[str, ...]:
        """The arm sides this session reads, in the order they were given."""
        return tuple(self._boards)

    def board(self, side: str) -> ArmStateBoard:
        """The board one side's readings are published to.

        Args:
            side: The arm side, as named in `read_arms`.

        Returns:
            (ArmStateBoard) That side's board.

        Raises:
            KeyError: If this session reads no such side.
        """
        return self._boards[side]

    @property
    def deadman(self) -> DeadmanController:
        """The lease canon, built over this session's latch."""
        return self._deadman

    def engage_safety_latch(self, reason: LatchReason) -> None:
        """Engage the one latch — the deadman's expiry path and the GUI stop both land here.

        Args:
            reason: Cause and timestamp of the latch. The latch keeps the first one.
        """
        self._latch.engage(reason)

    def acknowledge_latch(self) -> None:
        """Clear the latch. Reached only through the deadman's re-arm confirmation."""
        self._latch.acknowledge()

    @property
    def latch_active(self) -> bool:
        """Whether the latch is held.

        Returns:
            (bool) True between an engage and an operator-confirmed re-arm.
        """
        return self._latch.is_active

    @property
    def latch_reason(self) -> LatchReason | None:
        """What put the arm into a latched hold, or None while released.

        Exposed because `latch_active` alone cannot answer the question an operator facing a
        held arm actually has. The latch keeps the *first* reason, so this is the cause rather
        than the most recent re-assertion of the state.

        Returns:
            (LatchReason | None) The recorded attribution.
        """
        return self._latch.reason

    def tick(self) -> None:
        """Poll the deadman, read every side once, and publish each read to its own board.

        The deadman goes first because its own call contract says so: a lease that lapsed since
        the previous tick is latched before anything acts on this one's readings.

        Each read is stamped after it returns, not before it is issued, and each side is stamped
        separately. An age measured from the start of the tick omits the round trip, and the
        round trip is the term that grows when the bus is in trouble — so the number would be
        smallest exactly when the staleness it feeds matters most. Stamping both sides with one
        reading would hide the same gap between them.

        A side that raises stops the tick, and the sides already published this tick keep their
        new frames while the rest keep their previous ones. That is a mixed board state and it is
        the honest one: the alternative is publishing nothing for an arm that answered, which
        ages a reading that is not actually stale. The index is what tells them apart.

        Raises:
            Exception: Whatever a read raised, untouched. A tick that cannot read is a finding
                for whoever drives the loop, and swallowing it here would leave a board that
                silently stopped advancing.
        """
        self._deadman.poll()
        self._tick_index += 1
        for side, read_arm in self._read_arms.items():
            joint_deg, torque_nm, guard = read_arm()
            self._boards[side].publish(
                ArmState(
                    read_at=self._clock.now(),
                    joint_deg=joint_deg,
                    torque_nm=torque_nm,
                    guard=guard,
                    tick_index=self._tick_index,
                )
            )


__all__ = [
    "ArmFrame",
    "ArmReader",
    "ArmSession",
]
