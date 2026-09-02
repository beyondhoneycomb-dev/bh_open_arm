"""The one place a reader learns what the arm is doing, without touching the bus.

Two threads wanting one device is the shape this exists to remove. Today the control path reads
the arm inside `send_action` and anything else that wants to know — a guard, a chart, a stop
decision — has to read it again, which means a second bus owner, contention on a lock that is not
reentrant, and a pose paired with a torque that came from a different frame. The sibling Indy7 rig
measured that arrangement costing `loop.work` spikes of 74-80 ms against a 10 ms period, and the
spikes were failing register reads burning their full timeout while the control loop waited.

The fix is not a faster read. It is that **the tick reads once and everybody else reads the
board**:

    bus owner:   read all fitted motors -> publish(ArmState)   (one writer, once per tick)
    readers:     board.view()                                   (an attribute read, no lock)

`publish` swaps one frozen object into one attribute. CPython guarantees that store is atomic, so
a reader either sees the whole previous state or the whole new one and never a half-written mix —
which is why no lock appears here, and why `ArmState` must stay frozen. A mutable payload would
put the tearing back with the lock gone.

The board is owned by whoever owns the arm, never a module global. Two followers, or two tests,
sharing a process would otherwise judge each other's arm.

**Staleness needs two facts, not one.** The obvious rule — "a reading older than N seconds means
stop" — is wrong, and the sibling rig's suite said so within one run: a connected GUI sitting
between operator actions reads nothing and drives nothing, and that rule stops the arm for
standing still. An arm nobody reads and nobody drives is idle. An arm still being *commanded*
past a reading that stopped advancing is a loop driving blind, and only the second is a failure.
So the board also records when a frame last went out (`mark_commanded`), and
`ArmStateView.is_driving_blind` needs both: a command newer than the reading it was based on, and
an age past the deadline. A healthy loop reads then sends, so its last command is always newer
than its last read by up to one period — which is why the arming condition is a command that
outlives its reading, not merely a command.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.actuation.clock import Clock
from backend.actuation.guard import GuardSample
from contracts.units import Celsius, Deg, DegPerSec, Nm

# What `mark_commanded` records before any frame has gone out. Negative infinity rather than the
# clock's zero: a board that has published a reading but never sent must not read as "commanded
# at time 0", which on a monotonic clock is in the past and would arm the blind-driving latch on
# the first reading.
NEVER_COMMANDED = float("-inf")


@dataclass(frozen=True)
class ArmState:
    """One tick's reading of the arm, whole.

    Frozen because the board publishes it by swapping a reference: a mutable payload would let a
    reader see a field the writer was still filling, which is the tearing the lock-free swap
    exists to avoid.

    Attributes:
        read_at: The monotonic instant the read completed, on the board's clock.
        joint_deg: Per-joint angle, in the frozen command layout's order.
        torque_nm: Per-joint reported torque, from the SAME frame as `joint_deg`. Pairing them
            here is the point: read separately they describe two different instants, and a
            residual computed across that gap is a collision signal nobody can trust.
        velocity_deg_s: Per-joint reported velocity, from that same frame.
        temp_mos_c: Per-joint MOSFET temperature from that same frame, or None when the
            source has no thermometer. The only channel that says an arm is cooking, and it
            costs nothing to carry — the motor answers it in the frame the pose came in. None
            rather than zeros, because a CAN-free double has no MOSFET and `Celsius(0.0)` is a
            reading nothing downstream can tell from a measurement.
        temp_rotor_c: Per-joint rotor temperature, on the same terms.
        guard: What that one read told the collision guard — presence, bus health, lock, residual.
        tick_index: The scheduler tick this reading belongs to, so a reader can tell two
            consecutive publications apart even when every value in them is identical.
    """

    read_at: float
    joint_deg: tuple[Deg, ...]
    torque_nm: tuple[Nm, ...]
    velocity_deg_s: tuple[DegPerSec, ...]
    temp_mos_c: tuple[Celsius, ...] | None
    temp_rotor_c: tuple[Celsius, ...] | None
    guard: GuardSample
    tick_index: int


@dataclass(frozen=True)
class ArmStateView:
    """A reader's answer: the last state published, and what the clock says about it.

    Attributes:
        state: The last published reading, or None when the board has published none.
        age_s: Seconds since that reading, or infinity when there is none.
        commanded_since_read: Whether a frame went out after the reading was taken.
    """

    state: ArmState | None
    age_s: float
    commanded_since_read: bool

    def is_driving_blind(self, max_age_s: float) -> bool:
        """Whether a loop is still commanding past readings that stopped advancing.

        Both halves are required, and the second is the one that costs a test to find. An arm
        nobody reads and nobody drives is idle, not stale; latching on age alone stops an arm for
        standing still. What is a failure is a command that outlived the reading it was built on
        by more than the deadline — that is a loop putting frames on the bus with no idea where
        the joint is.

        Args:
            max_age_s: How old a reading may be while frames are still going out.

        Returns:
            (bool) True when the arm is being commanded past a reading that has gone stale.
        """
        return self.commanded_since_read and self.age_s > max_age_s


@dataclass
class ArmStateBoard:
    """One writer, any number of readers, no lock.

    The writer is whoever owns the bus. It calls `publish` once per tick with that tick's single
    read, and `mark_commanded` at the one point a frame leaves. Readers call `view`.

    Attributes:
        clock: The monotonic source ages are computed against. The same clock the scheduler
            reads, so an age here and a freshness decision there cannot disagree.
    """

    clock: Clock
    _state: ArmState | None = field(default=None, init=False)
    _commanded_at: float = field(default=NEVER_COMMANDED, init=False)

    def publish(self, state: ArmState) -> None:
        """Make one reading the current one.

        A single attribute store, which CPython performs atomically — that is the whole
        concurrency argument, and it holds only while `ArmState` stays frozen.

        Args:
            state: The reading this tick took.
        """
        self._state = state

    def mark_commanded(self, at: float) -> None:
        """Record that a frame went out, so staleness can tell a driven arm from an idle one.

        Called at the single send point rather than by each producer: a caller that forgot would
        leave the arm looking idle while it was being driven, which is the exact case the
        deadline exists to catch.

        Args:
            at: The monotonic instant the frame left.
        """
        self._commanded_at = at

    def view(self) -> ArmStateView:
        """Return the current reading and what the clock says about it.

        Returns:
            (ArmStateView) The last published state, its age, and whether a frame has gone out
            since it was taken.
        """
        state = self._state
        if state is None:
            return ArmStateView(state=None, age_s=float("inf"), commanded_since_read=False)
        return ArmStateView(
            state=state,
            age_s=self.clock.now() - state.read_at,
            commanded_since_read=self._commanded_at > state.read_at,
        )
