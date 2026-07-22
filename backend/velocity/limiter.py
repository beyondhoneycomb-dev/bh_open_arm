"""The bootstrap velocity limiter (WP-2A-04): scale, ramp-down, arming, refinement.

This is the runtime `WP-2A-04` stands up before the sweep (`PG-VEL-001`) ever runs. It is
distinct from the gateway velocity CHECK (`backend.actuation.safety.SafetyFilter`, which
REJECTS a command whose implied velocity exceeds the ceiling): this limiter SCALES and
ramps a commanded velocity down to a bounded one and admits it. The two compose — the
producer-side limiter keeps commands under the scaled ceiling, and the gateway check is the
independent backstop that stops anything that still exceeds the limit. Neither re-implements
the other.

Four properties the acceptance criteria fix (`02b` §1.2):

  * Active without `PG-VEL-001` (①): an armed limiter carries a validated limit set, and
    `assert_arming_permitted` refuses torque-ON when none is loaded. The default limiter
    arms at the WP-1-06 bootstrap magnitudes with no gate required.
  * Never exceeds the scaled active limit (③) and defaults to ≤10% scale (④): every output
    is clamped to `value × scale × ramp`, and `scale ≤ 1`, so no output ever passes the
    scaled active ceiling.
  * Ramp-down in the last-5-degree band (⑤): motion toward an operational position limit is
    attenuated to zero at the bound; motion away is never attenuated.
  * Refinement only by explicit approval and a new version (⑥): `refine` refuses a set with
    no approval, a non-increasing version, or a basis that cites its own measurement — the
    last reusing the WP-1-06 self-approval refusal, because a derived limit may never come
    from measurement.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.actuation.safety import SafetyLimits
from backend.safety_bringup.velocity import (
    assert_derivation_basis_not_self,
    assert_velocity_limit_active_by_default,
    velocity_limiter_default,
)
from backend.velocity.constants import (
    DEFAULT_GLOBAL_SCALE,
    MAX_GLOBAL_SCALE,
    MIN_GLOBAL_SCALE,
    RAMP_DOWN_BAND_DEG,
)
from backend.velocity.derivation import LimitSet, bootstrap_limit_set
from contracts.units import Deg, Rad, deg_to_rad, rad_to_deg


class LimiterNotArmedError(RuntimeError):
    """Raised when torque-ON or a limit call is attempted with no limit set loaded.

    Acceptance ① makes the loaded limit set the precondition for torque-ON: a limiter with
    no active set cannot bound anything, so it must refuse rather than pass a command
    through unlimited. This is the guard that keeps the arm from powering on without a
    velocity ceiling in force.
    """


class RefinementRefusedError(RuntimeError):
    """Raised when a refinement lacks explicit approval or a strictly greater version.

    Acceptance ⑥ allows the canonical set to replace the bootstrap set only through an
    explicit operator approval and a new version. A refinement that omits either is
    refused, so a limit set can never be swapped silently or rolled backward.
    """


class ScaleOutOfRangeError(ValueError):
    """Raised when a global scale falls outside `[0, 1]` (0–100%).

    A scale above one would place the effective ceiling above the derived active limit the
    scale exists to sit under, defeating acceptance ③; a negative scale is meaningless.
    """


@dataclass(frozen=True)
class RefinementApproval:
    """The explicit operator approval a refinement requires (acceptance ⑥).

    Attributes:
        operator: The operator authorising the replacement; empty is refused.
        reason: Why the refinement is being applied (audit provenance).
        result_record_uri: The `PG-VEL-001` result the refinement is authorised by, against
            which the new set's basis is checked for self-approval — a refined set may not
            cite this very record as its derivation basis.
    """

    operator: str
    reason: str
    result_record_uri: str

    def validate(self) -> None:
        """Refuse an approval with no operator or no result record.

        Raises:
            RefinementRefusedError: When the operator or result-record URI is empty.
        """
        if not self.operator:
            raise RefinementRefusedError("refinement approval names no operator")
        if not self.result_record_uri:
            raise RefinementRefusedError("refinement approval cites no PG-VEL-001 result record")


@dataclass(frozen=True)
class LimitResult:
    """The outcome of limiting one command tick.

    Attributes:
        scaled_rad_s: The admitted per-joint velocities, each within its applied ceiling.
        scaled_ceiling_rad_s: The scaled active limit per joint (`value × scale`), pre-ramp.
        applied_ceiling_rad_s: The ceiling actually applied (`value × scale × ramp`).
        ramped_joints: Joints where ramp-down attenuated the ceiling (inside the 5° band).
        clamped_joints: Joints where the command was clamped down to the applied ceiling.
    """

    scaled_rad_s: tuple[float, ...]
    scaled_ceiling_rad_s: tuple[float, ...]
    applied_ceiling_rad_s: tuple[float, ...]
    ramped_joints: tuple[int, ...]
    clamped_joints: tuple[int, ...]


@dataclass(frozen=True)
class StepResult:
    """The dt-based outcome of limiting a position step (jog-path application).

    Attributes:
        admissible_target_deg: The target after integrating the limited velocity over dt.
        velocity: The per-joint velocity limiting produced.
    """

    admissible_target_deg: tuple[Deg, ...]
    velocity: LimitResult


def ramp_bounds_from_safety_limits(limits: SafetyLimits) -> tuple[tuple[Deg, Deg], ...]:
    """Reuse the Wave-1 operational envelope as the ramp-down band source.

    The ramp-down band is measured against the canonical operational position limits, whose
    single owner is the Wave-1 `SafetyLimits` (`FR-SAF-045` selection). This limiter does
    not keep its own copy of those bounds; it reads them from a `SafetyLimits` so there is
    one source of truth for where a joint's limit is.

    Args:
        limits: The Wave-1 safety limit envelope.

    Returns:
        (tuple) The per-joint operational `(low, high)` bounds, in degrees.
    """
    return limits.operational_deg


class VelocityLimiter:
    """A dt-based global-scale velocity limiter with near-limit ramp-down (WP-2A-04).

    Ownership: holds the active limit set (which it does not derive — the magnitudes are the
    WP-1-06 canon), the control period, and the global scale. It writes no bus and rejects
    nothing; it produces a bounded velocity a producer publishes, and the single gateway
    remains the enforcement point. A limiter with no limit set is unarmed and refuses both
    limiting and torque-ON.
    """

    def __init__(self, dt_sec: float, scale: float, limit_set: LimitSet | None) -> None:
        """Bind the limiter to a control period, a global scale, and a limit set.

        Args:
            dt_sec: The control period the dt-based step application integrates over.
            scale: The global velocity scale in `[0, 1]`; the default path uses ≤10%.
            limit_set: The active limit set, or None for an unarmed limiter (torque-ON is
                refused until a set is loaded).

        Raises:
            ValueError: If `dt_sec` is not positive.
            ScaleOutOfRangeError: If `scale` is outside `[0, 1]`.
            DerivationBasisError: If a supplied limit set has an incomplete derivation basis.
        """
        if dt_sec <= 0.0:
            raise ValueError(f"control period dt_sec must be positive, got {dt_sec}")
        if scale < MIN_GLOBAL_SCALE or scale > MAX_GLOBAL_SCALE:
            raise ScaleOutOfRangeError(
                f"global scale {scale} is outside [{MIN_GLOBAL_SCALE}, {MAX_GLOBAL_SCALE}]"
            )
        if limit_set is not None:
            limit_set.validate()
        self._dt_sec = dt_sec
        self._scale = scale
        self._limit_set = limit_set

    @property
    def dt_sec(self) -> float:
        """The control period the step application integrates over."""
        return self._dt_sec

    @property
    def scale(self) -> float:
        """The global velocity scale in `[0, 1]`."""
        return self._scale

    @property
    def limit_set(self) -> LimitSet | None:
        """The active limit set, or None when the limiter is unarmed."""
        return self._limit_set

    @property
    def armed(self) -> bool:
        """Whether a validated limit set is loaded (the torque-ON precondition)."""
        return self._limit_set is not None

    def assert_arming_permitted(self) -> None:
        """Refuse torque-ON when no limit set is loaded (acceptance ①).

        Raises:
            LimiterNotArmedError: When the limiter carries no active limit set.
        """
        if self._limit_set is None:
            raise LimiterNotArmedError(
                "velocity limiter has no active limit set; torque-ON is refused until a "
                "derived limit set is loaded (02b §1.2 acceptance ①)"
            )

    def scaled_ceiling_rad_s(self) -> tuple[float, ...]:
        """The scaled active limit per joint (`value × scale`), before ramp-down.

        Returns:
            (tuple) The per-joint scaled ceiling, rad/s.

        Raises:
            LimiterNotArmedError: When the limiter is unarmed.
        """
        limit_set = self._require_armed()
        return tuple(value * self._scale for value in limit_set.values_rad_s)

    def limit_velocity(
        self,
        commanded_rad_s: tuple[float, ...],
        present_deg: tuple[Deg, ...],
        position_limits_deg: tuple[tuple[Deg, Deg], ...],
    ) -> LimitResult:
        """Scale and ramp a commanded velocity to a bounded one (acceptances ③⑤).

        Each joint's ceiling is `value × scale × ramp`, where `ramp` falls linearly to zero
        as the joint enters the last `RAMP_DOWN_BAND_DEG` degrees toward the operational
        limit in the direction of motion. The command is clamped to `[-ceiling, +ceiling]`,
        so the output never exceeds the scaled active limit and decelerates near a bound.

        Args:
            commanded_rad_s: The producer's requested per-joint velocities, rad/s.
            present_deg: The present joint positions, degrees.
            position_limits_deg: The operational `(low, high)` bounds per joint, degrees —
                sourced from the Wave-1 `SafetyLimits` via `ramp_bounds_from_safety_limits`.

        Returns:
            (LimitResult) The bounded velocities and the ceilings that produced them.

        Raises:
            LimiterNotArmedError: When the limiter is unarmed.
            ValueError: When the input widths disagree with the limit-set width.
        """
        limit_set = self._require_armed()
        self._check_width(commanded_rad_s, present_deg, position_limits_deg, limit_set.width)

        scaled: list[float] = []
        scaled_ceilings: list[float] = []
        applied_ceilings: list[float] = []
        ramped: list[int] = []
        clamped: list[int] = []
        for index, command in enumerate(commanded_rad_s):
            value = limit_set.values_rad_s[index]
            scaled_ceiling = value * self._scale
            low, high = position_limits_deg[index]
            ramp = _ramp_factor(present_deg[index], low, high, moving_positive=command >= 0.0)
            applied_ceiling = scaled_ceiling * ramp
            bounded = _clamp(command, applied_ceiling)
            scaled.append(bounded)
            scaled_ceilings.append(scaled_ceiling)
            applied_ceilings.append(applied_ceiling)
            if ramp < 1.0:
                ramped.append(index)
            if bounded != command:
                clamped.append(index)
        return LimitResult(
            scaled_rad_s=tuple(scaled),
            scaled_ceiling_rad_s=tuple(scaled_ceilings),
            applied_ceiling_rad_s=tuple(applied_ceilings),
            ramped_joints=tuple(ramped),
            clamped_joints=tuple(clamped),
        )

    def limit_step(
        self,
        target_deg: tuple[Deg, ...],
        present_deg: tuple[Deg, ...],
        safety_limits: SafetyLimits,
    ) -> StepResult:
        """Limit a position step by bounding its implied velocity over dt (jog-path use).

        The implied velocity is `(target − present) / dt` in radians per second; it is
        limited by `limit_velocity`, and the admissible target is `present` re-integrated
        from the bounded velocity over dt. The operational bounds for ramp-down are read
        from the Wave-1 `SafetyLimits`, reusing its envelope rather than restating limits.

        Args:
            target_deg: The producer's requested per-joint target positions, degrees.
            present_deg: The present joint positions, degrees.
            safety_limits: The Wave-1 limit envelope supplying the ramp-down bounds.

        Returns:
            (StepResult) The admissible target and the velocity-limiting detail.

        Raises:
            LimiterNotArmedError: When the limiter is unarmed.
            ValueError: When the input widths disagree with the limit-set width.
        """
        position_limits = ramp_bounds_from_safety_limits(safety_limits)
        implied = tuple(
            _delta_rad(target, present) / self._dt_sec
            for target, present in zip(target_deg, present_deg, strict=True)
        )
        result = self.limit_velocity(implied, present_deg, position_limits)
        admissible = tuple(
            _integrate_deg(present, velocity, self._dt_sec)
            for present, velocity in zip(present_deg, result.scaled_rad_s, strict=True)
        )
        return StepResult(admissible_target_deg=admissible, velocity=result)

    def refine(self, new_set: LimitSet, approval: RefinementApproval) -> VelocityLimiter:
        """Replace the active set with a refined one — only by approval and a new version.

        Acceptance ⑥: the swap requires an explicit operator approval and a strictly greater
        version, and the new set's basis must not cite the `PG-VEL-001` result that
        authorised it (the WP-1-06 self-approval refusal, reused). On success a new limiter
        carrying the refined set is returned and the previous set is superseded.

        Args:
            new_set: The refined limit set (`PG-VEL-001`-verified).
            approval: The explicit operator approval and the authorising result record.

        Returns:
            (VelocityLimiter) A new limiter at the same dt and scale, armed with `new_set`.

        Raises:
            RefinementRefusedError: When the approval is incomplete or the version does not
                strictly increase.
            DerivationBasisError: When the refined set's basis is incomplete.
            DerivationSelfApprovalError: When the refined set cites its own result record.
        """
        approval.validate()
        new_set.validate()
        if self._limit_set is not None and new_set.version <= self._limit_set.version:
            raise RefinementRefusedError(
                f"refinement version {new_set.version} does not exceed the active version "
                f"{self._limit_set.version}; a refinement requires a new set version "
                "(02b §1.2 acceptance ⑥)"
            )
        assert_derivation_basis_not_self(new_set.basis_uris, approval.result_record_uri)
        return VelocityLimiter(self._dt_sec, self._scale, new_set)

    def with_scale(self, scale: float) -> VelocityLimiter:
        """Return a limiter identical but for the global scale.

        Args:
            scale: The new global scale in `[0, 1]`.

        Returns:
            (VelocityLimiter) A new limiter at the given scale.

        Raises:
            ScaleOutOfRangeError: If `scale` is outside `[0, 1]`.
        """
        return VelocityLimiter(self._dt_sec, scale, self._limit_set)

    def _require_armed(self) -> LimitSet:
        """Return the active limit set or refuse when the limiter is unarmed."""
        if self._limit_set is None:
            raise LimiterNotArmedError(
                "velocity limiter has no active limit set; it cannot bound a command "
                "(02b §1.2 acceptance ①)"
            )
        return self._limit_set

    def _check_width(
        self,
        commanded_rad_s: tuple[float, ...],
        present_deg: tuple[Deg, ...],
        position_limits_deg: tuple[tuple[Deg, Deg], ...],
        width: int,
    ) -> None:
        """Refuse inputs whose widths disagree with the limit-set width."""
        widths = (len(commanded_rad_s), len(present_deg), len(position_limits_deg))
        if any(actual != width for actual in widths):
            raise ValueError(
                f"input widths {widths} disagree with limit-set width {width}; the velocity "
                "limiter operates over the arm joints its limit set declares"
            )


def _ramp_factor(present: Deg, low: Deg, high: Deg, moving_positive: bool) -> float:
    """The near-limit ramp-down factor in `[0, 1]` for one joint (acceptance ⑤).

    Motion toward the bound is attenuated inside the last `RAMP_DOWN_BAND_DEG` degrees and
    is zero at (or past) the bound; motion away from the bound is never attenuated.

    Args:
        present: The present joint position, degrees.
        low: The operational lower bound, degrees.
        high: The operational upper bound, degrees.
        moving_positive: Whether the command moves the joint toward the upper bound.

    Returns:
        (float) The ramp factor to apply to the scaled ceiling.
    """
    distance = high.value - present.value if moving_positive else present.value - low.value
    if distance >= RAMP_DOWN_BAND_DEG:
        return 1.0
    if distance <= 0.0:
        return 0.0
    return distance / RAMP_DOWN_BAND_DEG


def _clamp(value: float, ceiling: float) -> float:
    """Clamp a signed velocity to `[-ceiling, +ceiling]` (ceiling is non-negative)."""
    if value > ceiling:
        return ceiling
    if value < -ceiling:
        return -ceiling
    return value


def _delta_rad(target: Deg, present: Deg) -> float:
    """The signed `target − present` step, converted degrees→radians at the one crossing."""
    return deg_to_rad(target - present).value


def _integrate_deg(present: Deg, velocity_rad_s: float, dt_sec: float) -> Deg:
    """Integrate a bounded velocity over dt and add it to the present position (degrees)."""
    return present + rad_to_deg(Rad(velocity_rad_s * dt_sec))


def bootstrap_velocity_limiter(
    dt_sec: float, scale: float = DEFAULT_GLOBAL_SCALE
) -> VelocityLimiter:
    """Build the default limiter: armed at the WP-1-06 bootstrap magnitudes (acceptance ①④).

    This is the limiter that stands before the sweep with no `PG-VEL-001` required. It arms
    at the bootstrap limit set and opens at the ≤10% default scale, and it reuses the
    WP-1-06 default-active assertion so a regression that flips the upstream no-limit default
    back on is caught here too.

    Args:
        dt_sec: The control period.
        scale: The global scale; defaults to the ≤10% bootstrap default.

    Returns:
        (VelocityLimiter) An armed limiter at the bootstrap set and the given scale.
    """
    assert_velocity_limit_active_by_default(velocity_limiter_default())
    return VelocityLimiter(dt_sec, scale, bootstrap_limit_set())
