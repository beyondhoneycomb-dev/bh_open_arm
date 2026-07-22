"""The single send_action enforcement point, assembled (`WP-1-03`).

`11` NFR-INF-008 makes one method the sole, un-bypassable gate. This is the object
that method delegates to: it composes the ordered `SafetyFilter`, the fail-closed
`CollisionGuard`, and the packet-drop counter into one `submit` call, and it is the
only place a producer's request is turned into a decision. It holds no CAN handle —
the decision it returns is written by the scheduler tick, the single writer
(`02a` §3.1 ①), so the enforcement point decides and the scheduler emits, and the
two together are why there is exactly one place torque can reach the bus.

Every decision records BOTH the pre-clamp request and the post-clamp accepted action
(`00` §8.3, acceptance ⑯). A rejected command is not a silent drop: the arm holds at
its present pose, so the "accepted" action of a rejection is the present-position
hold — both channels are always present. A one-sided frame is unconstructible here
(`GateFrame` requires both), the structural form of the rule the CTR-ACT contract's
`validate_frame` also enforces.

The MIT gains are validated before anything else (`03` FR-MOT-018, acceptance ⑦):
`kp` outside `[0,500]` or `kd` outside `[0,5]` is rejected rather than sent, because
the CAN encoder silently wraps an over-range gain — a wrapped stiffness is a
different, unrequested command that would run anyway.

The gateway works on plain degree vectors of the follower's own width; the fixed-16
CTR-ACT channel types are assembled at the bimanual dataset boundary, not here, so
one gateway serves a single 8-joint arm or the 16-joint pair.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.actuation.guard import CollisionGuard
from backend.actuation.safety import (
    KD_MAX,
    KD_MIN,
    KP_MAX,
    KP_MIN,
    CheckStage,
    FilterInput,
    MotionHistory,
    SafetyFilter,
    SafetyReason,
)
from contracts.action import ClampReason, SafetyOverride
from contracts.units import Deg, Nm, deg_to_rad

# A stop reason's audit `ClampReason`, for the `safetyOverride` on a rejection.
_REASON_TO_CLAMP = {
    SafetyReason.STALE_SOURCE: ClampReason.STALE_SOURCE,
    SafetyReason.COLLISION_LATCH: ClampReason.SAFETY_LATCH,
    SafetyReason.JOINT_LIMIT: ClampReason.JOINT_LIMIT,
    SafetyReason.TORQUE_EXCEEDS_PEAK: ClampReason.TORQUE_LIMIT,
}


@dataclass(frozen=True)
class GateFrame:
    """One enforcement decision's audit pair — request and accepted, always together.

    The audit contract (`00` §8.3, acceptance ⑯) is that the pre-clamp request and
    the post-clamp accepted action are recorded together or not at all: a
    post-clamp-only frame erases what intervention and clamp saturation would need.
    Both fields are mandatory here, so a one-sided frame is unconstructible — the
    separation is enforced by the shape, not by a runtime check that could lapse.

    Attributes:
        requested: The producer's pre-clamp position request, degrees.
        accepted: The admitted position vector (the present-pose hold on a
            rejection), so both channels are present for every recorded decision.
    """

    requested: tuple[Deg, ...]
    accepted: tuple[Deg, ...]


@dataclass(frozen=True)
class GateResult:
    """The outcome of one `submit`.

    Attributes:
        rejected: True when a stop-class check fired and no motion was admitted.
        reason: The single distinct reason the decisive check produced.
        stage: The ordered stage that produced `reason`, or None on a clean pass.
        accepted: The admitted position vector (present-pose hold on a rejection).
        override: The `safetyOverride` audit record.
        feedforward_torque_nm: The peak-clamped feed-forward torque routed to the MIT
            frame (`12` §2.7.0 tau release).
    """

    rejected: bool
    reason: SafetyReason
    stage: CheckStage | None
    accepted: tuple[Deg, ...]
    override: SafetyOverride
    feedforward_torque_nm: tuple[Nm, ...]


class ActuationGateway:
    """The single enforcement point: filter + guard + drop counter, no CAN handle.

    Ownership: holds the ordered `SafetyFilter`, the `CollisionGuard` whose latch it
    reads, and the motion history the rate checks difference against. It holds no
    `CanWriter` and no bus — a decision it reaches is written by the scheduler tick,
    never here (`02a` §3.1 ①). The gains it validates and the limits the filter
    enforces are passed in; the gateway owns neither threshold.
    """

    def __init__(
        self,
        safety_filter: SafetyFilter,
        guard: CollisionGuard,
        dt_sec: float,
        freshness_window_sec: float,
    ) -> None:
        """Assemble the enforcement point.

        Args:
            safety_filter: The ordered eight-check filter.
            guard: The fail-closed collision guard whose latch state gates commands.
            dt_sec: The control period the rate checks divide by.
            freshness_window_sec: Age past which a source is stale.
        """
        self._filter = safety_filter
        self._guard = guard
        self._dt_sec = dt_sec
        self._freshness_window_sec = freshness_window_sec
        self._width = safety_filter.limits.width
        self._prev_velocity_rad_s: tuple[float, ...] | None = None
        self._prev_accel_rad_s2: tuple[float, ...] | None = None
        self._frames: list[GateFrame] = []

    @property
    def frames(self) -> tuple[GateFrame, ...]:
        """The recorded request/accepted audit pairs, in submission order."""
        return tuple(self._frames)

    @property
    def guard(self) -> CollisionGuard:
        """The collision guard whose latch this gateway honours."""
        return self._guard

    def submit(
        self,
        request: tuple[Deg, ...],
        present: tuple[Deg, ...],
        *,
        calibrated: bool = True,
        source_age_sec: float = 0.0,
        require_stopped: bool = False,
        feedforward_torque_nm: tuple[Nm, ...] | None = None,
        kp: tuple[float, ...] | None = None,
        kd: tuple[float, ...] | None = None,
    ) -> GateResult:
        """Run the enforcement pipeline for one command and record the decision.

        Args:
            request: The producer's pre-clamp position request, degrees.
            present: The arm's present joint positions, degrees, the command departs
                from.
            calibrated: Whether the arm has an established zero this command
                (`WP-1-02`); passed per-command because it changes when the operator
                zeroes, and the zero check reads the live state, not a build-time one.
            source_age_sec: Age of the source target for the freshness check.
            require_stopped: Whether a soft stop is in effect (hold-only admitted).
            feedforward_torque_nm: Optional per-joint feed-forward torque; clamped by
                Peak Torque and routed to the MIT frame.
            kp: Optional per-joint stiffness gains to validate against `[0,500]`.
            kd: Optional per-joint damping gains to validate against `[0,5]`.

        Returns:
            (GateResult) The single decision, with a distinct reason on a stop and
            the recorded request/accepted pair either way.
        """
        gain_reason = self._validate_gains(kp, kd)
        if gain_reason is not None:
            return self._reject(request, present, gain_reason, None)

        history = MotionHistory(
            present_deg=present,
            prev_velocity_rad_s=self._prev_velocity_rad_s,
            prev_accel_rad_s2=self._prev_accel_rad_s2,
        )
        outcome = self._filter.evaluate(
            FilterInput(
                request=request,
                history=history,
                dt_sec=self._dt_sec,
                source_age_sec=source_age_sec,
                freshness_window_sec=self._freshness_window_sec,
                calibrated=calibrated,
                collision_latched=self._guard.is_latched,
                require_stopped=require_stopped,
                feedforward_torque_nm=feedforward_torque_nm,
            )
        )

        if outcome.rejected or outcome.accepted is None:
            return self._reject(request, present, outcome.reason, outcome.stage)

        self._advance_history(present, outcome.accepted)
        self._record(request, outcome.accepted)
        return GateResult(
            rejected=False,
            reason=outcome.reason,
            stage=outcome.stage,
            accepted=outcome.accepted,
            override=outcome.override,
            feedforward_torque_nm=outcome.feedforward_torque_nm,
        )

    def _validate_gains(
        self, kp: tuple[float, ...] | None, kd: tuple[float, ...] | None
    ) -> SafetyReason | None:
        """Return a gain reason when kp/kd is out of range, else None (`03` FR-MOT-018)."""
        if kp is not None and any(not KP_MIN <= value <= KP_MAX for value in kp):
            return SafetyReason.KP_OUT_OF_RANGE
        if kd is not None and any(not KD_MIN <= value <= KD_MAX for value in kd):
            return SafetyReason.KD_OUT_OF_RANGE
        return None

    def _reject(
        self,
        request: tuple[Deg, ...],
        present: tuple[Deg, ...],
        reason: SafetyReason,
        stage: CheckStage | None,
    ) -> GateResult:
        """Build a rejection: hold at present, record both channels, do not advance history."""
        self._record(request, present)
        return GateResult(
            rejected=True,
            reason=reason,
            stage=stage,
            accepted=present,
            override=SafetyOverride(
                override_active=True,
                clamp_reason=_REASON_TO_CLAMP.get(reason, ClampReason.JOINT_LIMIT),
                stale=reason is SafetyReason.STALE_SOURCE,
                latched=reason is SafetyReason.COLLISION_LATCH,
            ),
            feedforward_torque_nm=tuple(Nm(0.0) for _ in range(self._width)),
        )

    def _advance_history(self, present: tuple[Deg, ...], accepted: tuple[Deg, ...]) -> None:
        """Fold an accepted command into the velocity/accel history for the next command.

        Acceleration is left None until there is a prior velocity to difference against,
        so the second move is when acceleration first has a reference and the third is
        when jerk does — the same cold-start rule the filter's rate checks apply.
        """
        present_rad = [deg_to_rad(value).value for value in present]
        accepted_rad = [deg_to_rad(value).value for value in accepted]
        velocity = tuple(
            (a - p) / self._dt_sec for a, p in zip(accepted_rad, present_rad, strict=True)
        )
        prev_velocity = self._prev_velocity_rad_s
        if prev_velocity is None:
            self._prev_accel_rad_s2 = None
        else:
            self._prev_accel_rad_s2 = tuple(
                (v - pv) / self._dt_sec for v, pv in zip(velocity, prev_velocity, strict=True)
            )
        self._prev_velocity_rad_s = velocity

    def _record(self, request: tuple[Deg, ...], accepted: tuple[Deg, ...]) -> None:
        """Record a request/accepted pair; `GateFrame` makes both channels mandatory (⑯)."""
        self._frames.append(GateFrame(requested=request, accepted=accepted))
