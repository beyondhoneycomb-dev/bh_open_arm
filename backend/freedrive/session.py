"""The Freedrive session: deadman hold-to-activate, entry gates, and the exit-to-hold order.

This is the object that turns the path-(C) producer into an operable mode under the two safety
contracts spec 04 fixes:

* FR-MAN-029 — Freedrive activates only by a deadman (hold-to-activate). Releasing the hold, or
  letting the lease lapse, exits **immediately to a Cat-2 position hold**. There is no toggle and
  no auto-hold: the active state decays the moment heartbeats stop, so staying in Freedrive is an
  ongoing act, never a latched setting.
* The Damiao "kd must not be 0 in position control" rule (spec 04 §2.4) — the exit restores the
  hold damping in the **same** MIT frame that re-applies position stiffness, so a position
  command with kd=0 is never produced.

It reuses rather than re-implements: the deadman lease and its expiry-as-latch
(``backend.deadman`` on the actuation ``LeaseManager`` / ``SafetyLatch``), the single enforcement
gateway (``backend.actuation``), and the Cat-2 hold frame builder (``positions_to_batch``). The
one latch it holds is driven by both the deadman expiry and the gateway's collision guard, so
Freedrive has a single definition of "held", not two.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.actuation.clock import Clock
from backend.actuation.enforcement import ActuationGateway
from backend.actuation.gateway import positions_to_batch
from backend.actuation.guard import CollisionGuard
from backend.actuation.latch import SafetyLatch
from backend.actuation.lease import LeaseManager
from backend.actuation.safety import SafetyFilter, SafetyLimits
from backend.deadman import DeadmanController, LeaseRenewal, RenewalResult
from backend.deadman.constants import DEADMAN_LEASE_DURATION_SEC
from backend.freedrive.constants import (
    DEFAULT_EFFORT_HEADROOM,
    DEFAULT_KD_FREEDRIVE,
    FREEDRIVE_CONTROL_PERIOD_SEC,
    FREEDRIVE_FRESHNESS_WINDOW_SEC,
)
from backend.freedrive.effort import EffortSaturation, EffortSaturationCheck
from backend.freedrive.gate import FreedrivePath, FrictionGate
from backend.freedrive.producer import FreedriveFrame, FreedriveProducer
from backend.friction.model import FrictionParams
from backend.gravity.backend import GravityBackend
from contracts.action import ExecutedMitCommand
from contracts.units import Rad
from ops.cancel.scheduler import LatchReason

# The attribution stamped on the latch when Freedrive exits on an explicit operator release, so a
# release is distinguishable in the audit from a deadman timeout (whose reason the deadman owns).
_RELEASE_GATE_ID = "freedrive"
_RELEASE_PREVIOUS_STATE = "freedrive_active"
_RELEASE_NEW_STATE = "position_hold"


class EntryRefusal(Enum):
    """Why a Freedrive entry was refused (acceptance I/IV)."""

    FRICTION_GATE_BLOCKED = "friction_gate_blocked"
    EFFORT_SATURATED = "effort_saturated"
    DEADMAN_NOT_HELD = "deadman_not_held"


class HoldCause(Enum):
    """Why a Freedrive exit produced a position hold (acceptance II)."""

    OPERATOR_RELEASE = "operator_release"
    DEADMAN_TIMEOUT = "deadman_timeout"
    SAFETY_LATCH = "safety_latch"
    GATEWAY_HOLD = "gateway_hold"
    IDLE = "idle"


class TickMode(Enum):
    """What a Freedrive tick produced: an engaged Freedrive frame, or a position hold."""

    FREEDRIVE = "freedrive"
    HOLD = "hold"


@dataclass(frozen=True)
class ExitToHold:
    """A Cat-2 position hold a Freedrive exit produced, and the restored damping it carries.

    The exit re-commands position with the hold gains bundled into one MIT frame, so the restored
    kd rides with the position command and the forbidden (kp>0, kd=0) state never exists on the
    wire (acceptance III). ``zero_kd_position_commands`` counts any command that still commands
    position stiffness with zero damping; the contract is that it is always 0.

    Attributes:
        cause: Why the hold was produced.
        hold_commands: The per-joint Cat-2 position-hold MIT commands.
        restored_kd: The per-joint damping restored before position stiffness was applied.
    """

    cause: HoldCause
    hold_commands: tuple[ExecutedMitCommand, ...]
    restored_kd: tuple[float, ...]

    @property
    def zero_kd_position_commands(self) -> int:
        """The number of hold commands that stiffen position with zero damping (must be 0).

        Returns:
            (int) Count of commands with ``kp > 0`` and ``kd == 0`` — always 0 by construction.
        """
        return sum(1 for command in self.hold_commands if command.kp > 0.0 and command.kd == 0.0)


@dataclass(frozen=True)
class FreedriveEntry:
    """The outcome of a Freedrive entry attempt.

    Attributes:
        engaged: True when path (C) started; False when a gate refused it.
        refusal: The refusal reason when not engaged, else None.
        offered_paths: The Freedrive paths available under the friction gate.
        banner: The FR-MAN-035 sag banner when path (C) is unavailable, else None.
        effort: The effort-saturation verdict at the entry pose, or None when the friction gate
            refused before the pose was examined.
        frame: The first Freedrive frame when engaged, else None.
    """

    engaged: bool
    refusal: EntryRefusal | None
    offered_paths: tuple[FreedrivePath, ...]
    banner: str | None
    effort: EffortSaturation | None
    frame: FreedriveFrame | None


@dataclass(frozen=True)
class FreedriveTick:
    """The outcome of one Freedrive tick.

    Attributes:
        mode: Whether the tick drove Freedrive or produced a position hold.
        frame: The Freedrive frame when ``mode`` is FREEDRIVE, else None.
        exit: The position hold when ``mode`` is HOLD, else None.
        was_active: Whether Freedrive was active entering this tick.
    """

    mode: TickMode
    frame: FreedriveFrame | None
    exit: ExitToHold | None
    was_active: bool


def _normalize_kd(kd_freedrive: float | tuple[float, ...], width: int) -> tuple[float, ...]:
    """Broadcast a scalar Freedrive damping to every joint, or check a per-joint tuple's width.

    Args:
        kd_freedrive: A scalar applied to all joints, or one value per joint.
        width: The arm joint count.

    Returns:
        (tuple[float, ...]) The per-joint damping, ``width`` wide.

    Raises:
        ValueError: If a per-joint tuple does not match the width.
    """
    if isinstance(kd_freedrive, tuple):
        if len(kd_freedrive) != width:
            raise ValueError(
                f"kd_freedrive width {len(kd_freedrive)} does not match arm width {width}"
            )
        return kd_freedrive
    return tuple(float(kd_freedrive) for _ in range(width))


class FreedriveSession:
    """Deadman-gated gravity-comp Freedrive over the reused spine; one session per operator.

    Ownership/threading: not thread-safe — one session serves one operator loop. It holds the
    single latch that both the deadman expiry and the gateway collision guard drive, the reused
    lease, the path-(C) producer, and the entry gates. It never touches the bus; every command it
    yields is a value object the caller hands to the single writer.
    """

    def __init__(
        self,
        gravity_backend: GravityBackend,
        friction_params: tuple[FrictionParams, ...],
        safety_limits: SafetyLimits,
        gate: FrictionGate,
        clock: Clock,
        kd_freedrive: float | tuple[float, ...] = DEFAULT_KD_FREEDRIVE,
        effort_headroom: float = DEFAULT_EFFORT_HEADROOM,
        lease_duration_sec: float = DEADMAN_LEASE_DURATION_SEC,
    ) -> None:
        """Assemble the session over its reused collaborators.

        Args:
            gravity_backend: The single ``tau_grav(q)`` source (WP-2B-02).
            friction_params: Per-joint identified friction law (WP-2B-07), arm width.
            safety_limits: The clamp envelope the gateway enforces and the effort check reads the
                peak torque from — one source for both.
            gate: The PG-FRIC-001 gate deciding whether path (C) may start.
            clock: The monotonic clock the lease, the guard, and heartbeats share.
            kd_freedrive: Freedrive damping, scalar or per-joint (FR-MAN-030).
            effort_headroom: Peak-torque fraction the gravity term must stay under at entry.
            lease_duration_sec: The deadman lease horizon a hold heartbeat grants.
        """
        width = safety_limits.width
        self._clock = clock
        self._latch = SafetyLatch()
        self._last_guard_reason: LatchReason | None = None
        guard = CollisionGuard(on_latch=self._on_guard_latch, clock=clock)
        gateway = ActuationGateway(
            safety_filter=SafetyFilter(safety_limits),
            guard=guard,
            dt_sec=FREEDRIVE_CONTROL_PERIOD_SEC,
            freshness_window_sec=FREEDRIVE_FRESHNESS_WINDOW_SEC,
        )
        self._kd_freedrive = _normalize_kd(kd_freedrive, width)
        self._producer = FreedriveProducer(
            gravity_backend, friction_params, gateway, self._kd_freedrive
        )
        self._effort = EffortSaturationCheck(
            gravity_backend, safety_limits.peak_torque_nm, effort_headroom
        )
        self._gate = gate
        self._lease = LeaseManager(lease_duration_sec)
        self._deadman = DeadmanController(
            lease=self._lease,
            latch_target=self,
            clock=clock,
            lease_duration_sec=lease_duration_sec,
        )
        self._active = False
        self._sequence = 0

    # -- LatchTarget surface the deadman and the guard drive (one shared latch) --------------

    def engage_safety_latch(self, reason: LatchReason) -> None:
        """Engage the one shared safety latch (the deadman's expiry path calls this).

        Args:
            reason: Cause and timestamp of the latch.
        """
        self._latch.engage(reason)

    def acknowledge_latch(self) -> None:
        """Clear the safety latch — an operator ack, the sole release of a latched hold."""
        self._latch.acknowledge()

    @property
    def latch_active(self) -> bool:
        """Whether the shared safety latch is held.

        Returns:
            (bool) True until an operator ack after a latch.
        """
        return self._latch.is_active

    def _on_guard_latch(self, reason: LatchReason) -> None:
        """Record and engage on a collision-guard latch; the guard never writes the bus itself.

        Args:
            reason: The guard's latch cause and timestamp.
        """
        self._last_guard_reason = reason
        self._latch.engage(reason)

    # -- state ------------------------------------------------------------------------------

    @property
    def active(self) -> bool:
        """Whether Freedrive is currently engaged.

        Returns:
            (bool) True between a successful entry and the next hold.
        """
        return self._active

    @property
    def is_held(self) -> bool:
        """Whether the operator is currently holding: the lease is live and nothing is latched.

        Returns:
            (bool) True when a recent heartbeat keeps the lease live and no latch is set.
        """
        return not self._latch.is_active and not self._lease.is_expired(self._clock.now())

    @property
    def offered_paths(self) -> tuple[FreedrivePath, ...]:
        """The Freedrive paths the friction gate offers.

        Returns:
            (tuple[FreedrivePath, ...]) (A)/(B), plus (C) only on a friction pass.
        """
        return self._gate.offered_paths()

    @property
    def banner(self) -> str | None:
        """The FR-MAN-035 sag banner when path (C) is unavailable, else None.

        Returns:
            (str | None) The sag banner or None.
        """
        return self._gate.banner()

    # -- hold-to-activate -------------------------------------------------------------------

    def hold_heartbeat(self) -> RenewalResult:
        """Send one hold heartbeat — the operator's continued hold-to-activate press.

        Each heartbeat renews the reused deadman lease; the absence of heartbeats is what lets the
        lease lapse and Freedrive fall to a hold, which is the structural form of "no auto-hold".

        Returns:
            (RenewalResult) The deadman's verdict on this heartbeat; a heartbeat after a latch is
            refused (no auto-resume).
        """
        self._sequence += 1
        renewal = LeaseRenewal(
            generation=self._deadman.current_generation,
            sequence=self._sequence,
            issued_mono_client=self._clock.now(),
        )
        return self._deadman.receive_renewal(renewal)

    # -- entry ------------------------------------------------------------------------------

    def enter(self, q_entry: tuple[float, ...], dq_entry: tuple[float, ...]) -> FreedriveEntry:
        """Attempt to start gravity-comp Freedrive at an entry pose (acceptance I/IV).

        Entry is admitted only when, in order: the friction gate offers path (C); the gravity
        torque does not saturate the effort at the pose; and the operator is holding the deadman.
        Any failure returns a refusal that still carries the offered (A)/(B) paths and, when the
        gate blocked (C), the sag banner.

        Args:
            q_entry: The entry joint angles, radians, arm width.
            dq_entry: The entry joint velocities, radians per second, arm width.

        Returns:
            (FreedriveEntry) Engaged with the first frame, or a refusal with the reason.
        """
        if not self._gate.path_c_available:
            return FreedriveEntry(
                engaged=False,
                refusal=EntryRefusal.FRICTION_GATE_BLOCKED,
                offered_paths=self._gate.offered_paths(),
                banner=self._gate.banner(),
                effort=None,
                frame=None,
            )

        effort = self._effort.check(q_entry)
        if effort.saturated:
            return FreedriveEntry(
                engaged=False,
                refusal=EntryRefusal.EFFORT_SATURATED,
                offered_paths=self._gate.offered_paths(),
                banner=self._gate.banner(),
                effort=effort,
                frame=None,
            )

        if not self.is_held:
            return FreedriveEntry(
                engaged=False,
                refusal=EntryRefusal.DEADMAN_NOT_HELD,
                offered_paths=self._gate.offered_paths(),
                banner=self._gate.banner(),
                effort=effort,
                frame=None,
            )

        self._active = True
        frame = self._producer.produce_frame(q_entry, dq_entry)
        return FreedriveEntry(
            engaged=True,
            refusal=None,
            offered_paths=self._gate.offered_paths(),
            banner=self._gate.banner(),
            effort=effort,
            frame=frame,
        )

    # -- tick / exit ------------------------------------------------------------------------

    def tick(self, q: tuple[float, ...], dq: tuple[float, ...]) -> FreedriveTick:
        """Run one Freedrive tick: drive path (C), or exit to a Cat-2 hold (acceptance II/III).

        The deadman is polled first, so a lease that lapsed this tick latches before anything
        else. A latched or lapsed lease, or a gateway that held the command (a collision latch),
        exits Freedrive to a position hold; otherwise the path-(C) frame is produced.

        Args:
            q: Present joint angles, radians, arm width.
            dq: Present joint velocities, radians per second, arm width.

        Returns:
            (FreedriveTick) The engaged frame, or the position hold the exit produced.
        """
        latched_now = self._deadman.poll()
        was_active = self._active

        if latched_now:
            return self._hold_tick(q, HoldCause.DEADMAN_TIMEOUT, was_active)
        if self._latch.is_active:
            return self._hold_tick(q, HoldCause.SAFETY_LATCH, was_active)
        if self._lease.is_expired(self._clock.now()):
            return self._hold_tick(q, HoldCause.DEADMAN_TIMEOUT, was_active)
        if not self._active:
            return self._hold_tick(q, HoldCause.IDLE, was_active)

        frame = self._producer.produce_frame(q, dq)
        if not frame.engaged:
            self._active = False
            return FreedriveTick(
                mode=TickMode.HOLD,
                frame=frame,
                exit=self._build_hold(q, HoldCause.GATEWAY_HOLD),
                was_active=was_active,
            )
        return FreedriveTick(mode=TickMode.FREEDRIVE, frame=frame, exit=None, was_active=was_active)

    def release(self, q: tuple[float, ...]) -> ExitToHold:
        """Explicit hold-to-activate release: exit immediately to a Cat-2 position hold (II).

        FR-MAN-029 requires the release to hold immediately rather than wait for the lease to
        lapse. The latch is engaged so nothing auto-resumes; the exit restores damping before it
        commands position stiffness (III).

        Args:
            q: Present joint angles, radians, arm width.

        Returns:
            (ExitToHold) The Cat-2 hold and the restored damping.
        """
        self._active = False
        self.engage_safety_latch(self._release_reason())
        return self._build_hold(q, HoldCause.OPERATOR_RELEASE)

    def _hold_tick(self, q: tuple[float, ...], cause: HoldCause, was_active: bool) -> FreedriveTick:
        """Build a hold tick, exiting Freedrive if it was active."""
        self._active = False
        return FreedriveTick(
            mode=TickMode.HOLD,
            frame=None,
            exit=self._build_hold(q, cause),
            was_active=was_active,
        )

    def _build_hold(self, q: tuple[float, ...], cause: HoldCause) -> ExitToHold:
        """Build the Cat-2 position hold: restore the hold damping in the same frame as position.

        ``positions_to_batch`` bundles the hold kp and the restored hold kd into one MIT frame, so
        the restored damping (``kd = HOLD_RESTORE_KD > 0``) is applied with — never after — the
        position stiffness. A position command with kd=0 is unconstructible on this path.

        Args:
            q: Present joint angles, radians, arm width.
            cause: Why the hold was produced.

        Returns:
            (ExitToHold) The hold commands and the restored per-joint damping.
        """
        hold_commands = positions_to_batch(tuple(Rad(angle) for angle in q))
        restored_kd = tuple(command.kd for command in hold_commands)
        return ExitToHold(cause=cause, hold_commands=hold_commands, restored_kd=restored_kd)

    def _release_reason(self) -> LatchReason:
        """Build the latch attribution for an explicit operator release."""
        return LatchReason(
            gate_id=_RELEASE_GATE_ID,
            previous_state=_RELEASE_PREVIOUS_STATE,
            new_state=_RELEASE_NEW_STATE,
            latched_at=self._clock.now(),
        )


__all__ = [
    "EntryRefusal",
    "ExitToHold",
    "FreedriveEntry",
    "FreedriveSession",
    "FreedriveTick",
    "HoldCause",
    "TickMode",
]
