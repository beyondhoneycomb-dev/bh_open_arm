"""Acceptances ①③④⑤⑥ — arming, scaled-ceiling, default ≤10%, ramp-down, refinement.

The limiter is the producer-side SCALER/ramp, distinct from the gateway velocity CHECK that
REJECTS: these tests assert it bounds a command rather than stopping it, never lets an output
past the scaled active limit, decelerates into a position bound, refuses torque-ON with no
set loaded, and swaps the set only by explicit approval, a new version, and a non-measured
basis.
"""

from __future__ import annotations

import dataclasses

import pytest

from backend.actuation.safety import SafetyLimits
from backend.safety_bringup.velocity import DerivationSelfApprovalError
from backend.velocity.constants import DEFAULT_GLOBAL_SCALE
from backend.velocity.derivation import (
    DerivationBasisError,
    DerivedLimit,
    LimitSet,
    bootstrap_limit_set,
)
from backend.velocity.limiter import (
    LimiterNotArmedError,
    RefinementApproval,
    RefinementRefusedError,
    ScaleOutOfRangeError,
    VelocityLimiter,
    bootstrap_velocity_limiter,
    ramp_bounds_from_safety_limits,
)
from contracts.units import Deg, Nm, Rad, rad_to_deg

WIDTH = 7
DT_SEC = 0.02


def _arm_safety_limits(op_low: float = -90.0, op_high: float = 90.0) -> SafetyLimits:
    """A valid 7-wide Wave-1 limit envelope; ramp bounds come from `operational_deg`."""
    mechanical = tuple((Deg(-180.0), Deg(180.0)) for _ in range(WIDTH))
    operational = tuple((Deg(op_low), Deg(op_high)) for _ in range(WIDTH))
    limits = SafetyLimits(
        mechanical_deg=mechanical,
        operational_deg=operational,
        velocity_limit_rad_s=tuple(20.0 for _ in range(WIDTH)),
        accel_limit_rad_s2=tuple(50.0 for _ in range(WIDTH)),
        jerk_limit_rad_s3=tuple(500.0 for _ in range(WIDTH)),
        step_delta_limit_rad=tuple(0.5 for _ in range(WIDTH)),
        peak_torque_nm=tuple(Nm(40.0) for _ in range(WIDTH)),
        operational_torque_nm=tuple(Nm(30.0) for _ in range(WIDTH)),
    )
    limits.validate()
    return limits


def _present(deg: float) -> tuple[Deg, ...]:
    return tuple(Deg(deg) for _ in range(WIDTH))


def _refined_set(version: int, value: float, basis: tuple[str, ...]) -> LimitSet:
    limits = tuple(
        DerivedLimit(
            joint_index=index,
            motor_type="DM4310",
            value_rad_s=value,
            motor_vmax_rad_s=30.0,
            gear_ratio=10.0,
            source="pg_vel_001_command_following",
            formula="refined ceiling verified under the bootstrap limiter",
        )
        for index in range(WIDTH)
    )
    return LimitSet(version=version, provenance="refined", basis_uris=basis, limits=limits)


# ── ① active without PG-VEL-001; torque-ON blocked with no set ────────────────────────────


def test_default_limiter_is_armed_without_pg_vel_001() -> None:
    limiter = bootstrap_velocity_limiter(DT_SEC)
    assert limiter.armed
    limiter.assert_arming_permitted()  # does not raise


def test_torque_on_refused_when_no_limit_set_loaded() -> None:
    unarmed = VelocityLimiter(DT_SEC, DEFAULT_GLOBAL_SCALE, None)
    assert not unarmed.armed
    with pytest.raises(LimiterNotArmedError):
        unarmed.assert_arming_permitted()


def test_unarmed_limiter_refuses_to_bound_a_command() -> None:
    unarmed = VelocityLimiter(DT_SEC, DEFAULT_GLOBAL_SCALE, None)
    with pytest.raises(LimiterNotArmedError):
        unarmed.limit_velocity((0.0,) * WIDTH, _present(0.0), _arm_safety_limits().operational_deg)


# ── ④ default scale ≤ 10%; scale range ────────────────────────────────────────────────────


def test_default_scale_is_at_most_ten_percent() -> None:
    assert DEFAULT_GLOBAL_SCALE <= 0.10
    assert bootstrap_velocity_limiter(DT_SEC).scale == DEFAULT_GLOBAL_SCALE


def test_scale_above_one_is_refused() -> None:
    with pytest.raises(ScaleOutOfRangeError):
        VelocityLimiter(DT_SEC, 1.5, bootstrap_limit_set())


def test_negative_scale_is_refused() -> None:
    with pytest.raises(ScaleOutOfRangeError):
        VelocityLimiter(DT_SEC, -0.01, bootstrap_limit_set())


def test_non_positive_dt_is_refused() -> None:
    with pytest.raises(ValueError):
        VelocityLimiter(0.0, DEFAULT_GLOBAL_SCALE, bootstrap_limit_set())


# ── ③ no command exceeds the scaled active limit ──────────────────────────────────────────


def test_no_output_exceeds_the_scaled_active_limit() -> None:
    limiter = bootstrap_velocity_limiter(DT_SEC)
    bounds = _arm_safety_limits().operational_deg
    present = _present(0.0)  # mid-range: ramp factor is 1.0, so applied == scaled ceiling
    scaled_ceiling = limiter.scaled_ceiling_rad_s()
    for magnitude in (0.01, 0.5, 5.0, 100.0, -100.0, 1e6):
        commanded = tuple(magnitude for _ in range(WIDTH))
        result = limiter.limit_velocity(commanded, present, bounds)
        for index, out in enumerate(result.scaled_rad_s):
            assert abs(out) <= scaled_ceiling[index] + 1e-12


def test_command_within_ceiling_passes_unchanged() -> None:
    limiter = bootstrap_velocity_limiter(DT_SEC)
    bounds = _arm_safety_limits().operational_deg
    tiny = tuple(0.001 for _ in range(WIDTH))
    result = limiter.limit_velocity(tiny, _present(0.0), bounds)
    assert result.scaled_rad_s == tiny
    assert result.clamped_joints == ()


def test_command_above_ceiling_is_scaled_down_not_rejected() -> None:
    # Distinct from the gateway CHECK: the command is admitted at the ceiling, not stopped.
    limiter = bootstrap_velocity_limiter(DT_SEC)
    bounds = _arm_safety_limits().operational_deg
    fast = tuple(100.0 for _ in range(WIDTH))
    result = limiter.limit_velocity(fast, _present(0.0), bounds)
    assert result.clamped_joints == tuple(range(WIDTH))
    assert result.scaled_rad_s == limiter.scaled_ceiling_rad_s()


# ── ⑤ ramp-down in the last-5-degree band ─────────────────────────────────────────────────


def test_ramp_down_attenuates_toward_the_bound() -> None:
    limiter = bootstrap_velocity_limiter(DT_SEC)
    bounds = _arm_safety_limits(op_high=90.0).operational_deg
    present = _present(87.5)  # 2.5 deg from the high bound -> factor 0.5
    scaled_ceiling = limiter.scaled_ceiling_rad_s()
    result = limiter.limit_velocity(tuple(100.0 for _ in range(WIDTH)), present, bounds)
    for index, applied in enumerate(result.applied_ceiling_rad_s):
        assert applied == pytest.approx(scaled_ceiling[index] * 0.5)
    assert result.ramped_joints == tuple(range(WIDTH))


def test_ramp_down_is_zero_at_the_bound() -> None:
    limiter = bootstrap_velocity_limiter(DT_SEC)
    bounds = _arm_safety_limits(op_high=90.0).operational_deg
    result = limiter.limit_velocity(tuple(100.0 for _ in range(WIDTH)), _present(90.0), bounds)
    assert all(out == 0.0 for out in result.scaled_rad_s)


def test_no_ramp_at_band_edge() -> None:
    limiter = bootstrap_velocity_limiter(DT_SEC)
    bounds = _arm_safety_limits(op_high=90.0).operational_deg
    present = _present(85.0)  # exactly 5 deg from the bound -> factor 1.0
    result = limiter.limit_velocity(tuple(100.0 for _ in range(WIDTH)), present, bounds)
    assert result.ramped_joints == ()
    assert result.scaled_rad_s == limiter.scaled_ceiling_rad_s()


def test_motion_away_from_the_bound_is_not_ramped() -> None:
    limiter = bootstrap_velocity_limiter(DT_SEC)
    bounds = _arm_safety_limits(op_high=90.0, op_low=-90.0).operational_deg
    present = _present(89.0)  # 1 deg from high, but the command moves negative (away)
    result = limiter.limit_velocity(tuple(-100.0 for _ in range(WIDTH)), present, bounds)
    assert result.ramped_joints == ()
    assert result.scaled_rad_s == tuple(-c for c in limiter.scaled_ceiling_rad_s())


# ── dt-based step application reuses the Wave-1 SafetyLimits envelope ──────────────────────


def test_ramp_bounds_reuse_the_safety_limits_operational_envelope() -> None:
    limits = _arm_safety_limits(op_low=-45.0, op_high=45.0)
    assert ramp_bounds_from_safety_limits(limits) == limits.operational_deg


def test_limit_step_bounds_a_far_target_to_a_small_admissible_step() -> None:
    limiter = bootstrap_velocity_limiter(DT_SEC)
    limits = _arm_safety_limits()
    target = _present(90.0)  # far away; implied velocity is enormous
    admissible = limiter.limit_step(target, _present(0.0), limits)
    ceilings = limiter.scaled_ceiling_rad_s()
    for index, moved in enumerate(admissible.admissible_target_deg):
        expected_step = rad_to_deg(Rad(ceilings[index] * DT_SEC)).value
        assert moved.value == pytest.approx(expected_step)


# ── ⑥ refinement only by explicit approval, a new version, and a non-measured basis ───────


def test_refine_requires_a_strictly_greater_version() -> None:
    limiter = bootstrap_velocity_limiter(DT_SEC)  # bootstrap version 1
    approval = RefinementApproval(operator="mark", reason="pg-vel-001 pass", result_record_uri="r")
    same_version = _refined_set(version=1, value=1.0, basis=("spec/03#2.2",))
    with pytest.raises(RefinementRefusedError):
        limiter.refine(same_version, approval)


def test_refine_requires_explicit_approval() -> None:
    limiter = bootstrap_velocity_limiter(DT_SEC)
    no_operator = RefinementApproval(operator="", reason="", result_record_uri="r")
    refined = _refined_set(version=2, value=1.0, basis=("spec/03#2.2",))
    with pytest.raises(RefinementRefusedError):
        limiter.refine(refined, no_operator)


def test_refine_refuses_a_basis_that_cites_its_own_result_record() -> None:
    limiter = bootstrap_velocity_limiter(DT_SEC)
    approval = RefinementApproval(
        operator="mark", reason="pass", result_record_uri="pg-vel-001/run7"
    )
    self_approving = _refined_set(version=2, value=1.0, basis=("pg-vel-001/run7",))
    with pytest.raises(DerivationSelfApprovalError):
        limiter.refine(self_approving, approval)


def test_refine_refuses_a_set_with_incomplete_basis() -> None:
    limiter = bootstrap_velocity_limiter(DT_SEC)
    approval = RefinementApproval(operator="mark", reason="pass", result_record_uri="r")
    broken = dataclasses.replace(
        _refined_set(version=2, value=1.0, basis=("spec/03#2.2",)),
        limits=(dataclasses.replace(_refined_set(2, 1.0, ("s",)).limits[0], source=""),) * WIDTH,
    )
    with pytest.raises(DerivationBasisError):
        limiter.refine(broken, approval)


def test_refine_adopts_a_lower_verified_limit_and_supersedes_the_previous_set() -> None:
    # PG-VEL-001 measured limit below the derived value -> adopt the lower, old set stale.
    limiter = bootstrap_velocity_limiter(DT_SEC)
    approval = RefinementApproval(operator="mark", reason="pg-vel-001 pass", result_record_uri="r")
    lower = _refined_set(version=2, value=0.5, basis=("spec/03#2.2",))
    refined_limiter = limiter.refine(lower, approval)
    assert refined_limiter.limit_set is not None
    assert refined_limiter.limit_set.version == 2
    assert refined_limiter.limit_set.provenance == "refined"
    assert refined_limiter.limit_set.values_rad_s == tuple(0.5 for _ in range(WIDTH))
    # The original limiter is unchanged; the swap produced a new object.
    assert limiter.limit_set is not None
    assert limiter.limit_set.version == 1
