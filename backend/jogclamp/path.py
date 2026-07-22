"""The jog-path clamp application: two-stage position clamp + step-delta jump cap.

WP-2A-03. A jog producer (`WP-2A-01`) publishes a position target; before that
target reaches the single `send_action` gateway (`11` NFR-INF-008 — the
un-bypassable enforcement point that runs the Wave-1 `SafetyFilter`), the jog path
shapes it so a jog is smooth and pre-bounded. This module owns that shaping and
nothing else. It holds no CAN handle and it is NOT the enforcement point: the
gateway's ordered eight-check filter remains the backstop, and a value this path
lets through is still subject to every gateway check.

Reuse, not reimplementation (`02b` WP-2A-03 — the audit hunts for two sources of one
rule):

- The envelope is `SafetyLimits`, imported. This path invents no bound; it reads the
  mechanical, operational and step-delta limits from the one validated set, and its
  constructor runs `SafetyLimits.validate()`, so a profile whose operational envelope
  is not a subset of the mechanical one is refused at construction (acceptance ①) by
  the same Wave-1 check the gateway uses — never a second subset test.
- The velocity guard is NOT here. Velocity enforcement is the gateway's
  `SafetyFilter._check_slew`, a rad/s CHECK that stops the tick. This path never
  divides by a control period and never reads `velocity_limit_rad_s`; its jump guard
  caps the per-step position delta against `step_delta_limit_rad` and clips-and-
  proceeds. The two are separate code paths on purpose (acceptance ②): a step-delta
  jump limit of 1.8 rad/step reused as a velocity limit is 90 rad/s at 50 Hz, which
  is no limit at all (the negative branch).

What is genuinely new, and owned here:

- The two-stage clamp APPLICATION for the jog producer: clamp to mechanical, then to
  operational, each clip-and-proceed and each counted, so a request beyond the
  mechanical envelope (a producer fault) stays a distinct, attributable event from a
  request merely beyond the operational envelope (a normal operating clamp).
- `apply_jump_guard` / `_apply_step_cap`: the per-step jump cap, clip-and-proceed.
  This is producer-side smoothing, distinct in purpose from the gateway's step-delta
  STOP; the gateway STOP remains the backstop.
- `_previous_q_deg`, seeded from the present pose at connect (`seed_previous`), so the
  first jog send is guarded against the real pose rather than skipped the way a
  None-initialised `max_relative_target` skips it (acceptance ④).
- `ClampCounter`: clamps surface as a tally, not a silent `logger.debug` (③).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.actuation.safety import SafetyLimits
from backend.jogclamp.counter import ClampCounter
from backend.jogclamp.reason import JogClampReason, to_clamp_reason
from contracts.action import ClampReason
from contracts.units import Deg, Rad, deg_to_rad, rad_to_deg


class JogClampNotSeededError(RuntimeError):
    """Raised when the jog path shapes a target before `_previous_q_deg` is seeded.

    Seeding from the present pose at connect is what protects the first send (`04`
    FR-MAN-012, acceptance ④); an unseeded apply has no jump reference, so it is
    refused fail-closed rather than passed through unguarded.
    """


class JogClampConfigError(ValueError):
    """Raised when the limit set reaches the step cap without a step-delta guard.

    Unreachable through the constructor, which runs `SafetyLimits.validate()`; kept
    as a fail-closed assertion so a path that ever bypasses validation cannot make
    the jump guard silently vacuous.
    """


@dataclass(frozen=True)
class JogClampResult:
    """The shaped jog target and which clamps altered it, in pipeline order.

    Attributes:
        accepted_deg: The shaped target, degrees, the jog producer publishes.
        reasons: The clamps that fired this call, in mechanical → operational → step
            cap order; empty when the request passed through unaltered.
    """

    accepted_deg: tuple[Deg, ...]
    reasons: tuple[JogClampReason, ...]

    @property
    def clamped(self) -> bool:
        """Whether any stage altered the request."""
        return bool(self.reasons)

    def audit_reason(self) -> ClampReason:
        """The decisive clamp's frozen CTR-ACT audit reason, or NONE when unclamped.

        Returns:
            (ClampReason) The first fired clamp mapped to `CTR-ACT@v1`, else NONE.
        """
        if not self.reasons:
            return ClampReason.NONE
        return to_clamp_reason(self.reasons[0])


class JogClampPath:
    """The jog producer's pre-gateway shaping: staged clamp, jump cap, clamp counter.

    Ownership: holds the validated `SafetyLimits` envelope (which it does not own —
    the limits are passed in), a per-session `ClampCounter`, and the last shaped
    command as the jump-guard reference. It holds no CAN handle and no producer; it
    is a shaping function the jog producer calls before publishing to the mailbox.
    """

    def __init__(self, limits: SafetyLimits) -> None:
        """Bind the jog path to a validated limit envelope.

        Args:
            limits: The clamp envelope; `validate` runs here so the path can never be
                built around an operational envelope wider than the mechanical one, or
                a set that leaves the step-delta jump guard unset (acceptance ①). The
                subset and rate-guard checks are Wave-1's, reused, not reimplemented.

        Raises:
            SafetyConfigError: If the limit envelope is inconsistent.
        """
        limits.validate()
        self._limits = limits
        self._counter = ClampCounter()
        self._previous_q_deg: tuple[Deg, ...] | None = None

    @property
    def limits(self) -> SafetyLimits:
        """The validated limit envelope this path clamps against."""
        return self._limits

    @property
    def counter(self) -> ClampCounter:
        """The per-reason clamp tally surfaced instead of a silent log (③)."""
        return self._counter

    @property
    def previous_q_deg(self) -> tuple[Deg, ...] | None:
        """The last shaped command, the jump-guard reference, or None if unseeded."""
        return self._previous_q_deg

    @property
    def seeded(self) -> bool:
        """Whether the jump-guard reference has been seeded from a present pose."""
        return self._previous_q_deg is not None

    def seed_previous(self, present_deg: tuple[Deg, ...]) -> None:
        """Seed the jump-guard reference from the present pose at connect (④).

        The first jog send differences against this seed rather than being skipped,
        so it is protected from the outset. Called once at connect with the pose read
        back from the arm.

        Args:
            present_deg: The present joint pose, degrees, of the envelope's width.

        Raises:
            ValueError: If the pose width does not match the limit envelope.
        """
        if len(present_deg) != self._limits.width:
            raise ValueError(
                f"present pose width {len(present_deg)} does not match limit width "
                f"{self._limits.width}"
            )
        self._previous_q_deg = present_deg

    def apply(self, request_deg: tuple[Deg, ...]) -> JogClampResult:
        """Shape one jog target: clamp mechanical, clamp operational, cap the jump.

        The stages run in fixed order, each clip-and-proceed and each counted. The
        shaped command becomes the next call's jump-guard reference.

        Args:
            request_deg: The jog producer's pre-clamp target, degrees.

        Returns:
            (JogClampResult) The shaped target and the clamps that fired, in order.

        Raises:
            ValueError: If the request width does not match the limit envelope.
            JogClampNotSeededError: If applied before `seed_previous` (④): an unseeded
                first send would have no jump reference and is refused fail-closed.
        """
        if len(request_deg) != self._limits.width:
            raise ValueError(
                f"request width {len(request_deg)} does not match limit width {self._limits.width}"
            )
        if self._previous_q_deg is None:
            raise JogClampNotSeededError(
                "jog target shaped before seed_previous(); the first send must be seeded "
                "from the present pose so it is protected (04 FR-MAN-012)"
            )

        reasons: list[JogClampReason] = []
        working, hit = self.clamp_stage1(request_deg)
        if hit:
            reasons.append(JogClampReason.MECHANICAL_LIMIT)
            self._counter.record(JogClampReason.MECHANICAL_LIMIT)
        working, hit = self.clamp_stage2(working)
        if hit:
            reasons.append(JogClampReason.OPERATIONAL_LIMIT)
            self._counter.record(JogClampReason.OPERATIONAL_LIMIT)
        working, hit = self.apply_jump_guard(working)
        if hit:
            reasons.append(JogClampReason.STEP_CAP)
            self._counter.record(JogClampReason.STEP_CAP)

        self._previous_q_deg = working
        return JogClampResult(accepted_deg=working, reasons=tuple(reasons))

    def clamp_stage1(self, working: tuple[Deg, ...]) -> tuple[tuple[Deg, ...], bool]:
        """Clip a jog target to the mechanical URDF envelope — stage 1 of 2.

        A hit here means the raw request left the mechanical envelope, which the
        operational clip (stage 2) also bounds; the separate stage keeps that event
        attributable as a producer fault rather than a normal operating clamp.

        Args:
            working: The target to clip, degrees.

        Returns:
            (tuple) The clipped target and whether any joint was clipped.
        """
        return self._clip(working, self._limits.mechanical_deg)

    def clamp_stage2(self, working: tuple[Deg, ...]) -> tuple[tuple[Deg, ...], bool]:
        """Clip a jog target to the tighter operational envelope — stage 2 of 2.

        Args:
            working: The target to clip, degrees (already mechanical-clipped in the
                pipeline, but the method is total and clips whatever it is given).

        Returns:
            (tuple) The clipped target and whether any joint was clipped.
        """
        return self._clip(working, self._limits.operational_deg)

    def apply_jump_guard(self, working: tuple[Deg, ...]) -> tuple[tuple[Deg, ...], bool]:
        """Cap the per-step jump against the seeded reference (clip-and-proceed).

        This is the jog-path jump guard — a per-step position-delta cap, NOT a
        velocity limit. It never divides by a control period; velocity enforcement is
        the gateway's separate check (acceptance ②).

        Args:
            working: The target to cap, degrees.

        Returns:
            (tuple) The capped target and whether any joint was capped.

        Raises:
            JogClampNotSeededError: If called before `seed_previous` (④).
        """
        previous = self._previous_q_deg
        if previous is None:
            raise JogClampNotSeededError(
                "apply_jump_guard before seed_previous(); the jump guard has no reference "
                "(04 FR-MAN-012)"
            )
        return self._apply_step_cap(working, previous)

    def _clip(
        self, working: tuple[Deg, ...], envelope: tuple[tuple[Deg, Deg], ...]
    ) -> tuple[tuple[Deg, ...], bool]:
        """Clip each joint to its `(low, high)` bound; report whether anything moved.

        The one position-clip site in this module; both stages route through it so a
        second, drifting copy of the clip cannot appear.
        """
        clamped: list[Deg] = []
        hit = False
        for angle, (low, high) in zip(working, envelope, strict=True):
            bounded = Deg(min(max(angle.value, low.value), high.value))
            if bounded.value != angle.value:
                hit = True
            clamped.append(bounded)
        return tuple(clamped), hit

    def _apply_step_cap(
        self, working: tuple[Deg, ...], previous: tuple[Deg, ...]
    ) -> tuple[tuple[Deg, ...], bool]:
        """Cap each joint's delta from `previous` to the step-delta jump limit.

        The delta and its limit are compared in radians — the same unit and the same
        `step_delta_limit_rad` field the gateway's step-delta check reads — through
        the one sanctioned deg-rad crossing, so the jog cap and the gateway stop share
        the limit definition without sharing the code that enforces it.
        """
        step_limit = self._limits.step_delta_limit_rad
        if step_limit is None:
            raise JogClampConfigError(
                "step-delta jump guard is unset after validate(); the jump guard would be "
                "vacuous (14 FR-OPS-012)"
            )
        capped: list[Deg] = []
        hit = False
        for target, prior, limit_rad in zip(working, previous, step_limit, strict=True):
            delta_rad = deg_to_rad(target - prior).value
            cap_deg = rad_to_deg(Rad(limit_rad)).value
            if delta_rad > limit_rad:
                capped.append(Deg(prior.value + cap_deg))
                hit = True
            elif delta_rad < -limit_rad:
                capped.append(Deg(prior.value - cap_deg))
                hit = True
            else:
                capped.append(target)
        return tuple(capped), hit
