"""Acceptance ② — the derivation basis is on the artifact and a value with no basis is refused.

The load-bearing facts: the bootstrap magnitudes are the WP-1-06 canon (single source of
truth, not re-derived here), every joint carries formula/gear/motor-V_MAX/source, and a
limit or set with any basis field missing is load-refused rather than silently admitted.
"""

from __future__ import annotations

import dataclasses

import pytest

from backend.safety_bringup.velocity import bootstrap_limiter_rad_s
from backend.velocity.constants import GEAR_RATIO_BY_MOTOR
from backend.velocity.derivation import (
    DerivationBasisError,
    DerivedLimit,
    LimitSet,
    bootstrap_limit_set,
)


def _good_limit() -> DerivedLimit:
    return DerivedLimit(
        joint_index=0,
        motor_type="DM8009",
        value_rad_s=1.57,
        motor_vmax_rad_s=45.0,
        gear_ratio=9.0,
        source="velocity_cap_12_2_5",
        formula="ceiling = min(...)",
    )


def test_bootstrap_set_is_seven_arm_joints_version_one() -> None:
    limit_set = bootstrap_limit_set()
    assert limit_set.width == 7
    assert limit_set.version == 1
    assert limit_set.provenance == "bootstrap"


def test_bootstrap_magnitudes_are_the_wp1_06_canon_not_re_derived() -> None:
    # Single source of truth: the artifact reports exactly the WP-1-06 bootstrap magnitudes.
    assert bootstrap_limit_set().values_rad_s == bootstrap_limiter_rad_s()


def test_every_joint_carries_formula_gear_motor_vmax_and_source() -> None:
    # ②: the derivation formula, gear ratio and source are on the artifact.
    for limit in bootstrap_limit_set().limits:
        assert limit.formula
        assert limit.source
        assert limit.gear_ratio > 0.0
        assert limit.motor_vmax_rad_s > 0.0
        assert "min(" in limit.formula


def test_bootstrap_gear_ratios_match_the_motor_table() -> None:
    # `03` §2.2: DM8009 9:1, DM4340 40:1, DM4310 10:1.
    expected = {"DM8009": 9.0, "DM4340": 40.0, "DM4310": 10.0}
    for limit in bootstrap_limit_set().limits:
        assert limit.gear_ratio == expected[limit.motor_type]
        assert GEAR_RATIO_BY_MOTOR  # the constant is populated


def test_bootstrap_basis_uris_are_physical_sources_not_a_measurement() -> None:
    # ②: the basis cites datasheet / URDF / catalogue, never a rig result record.
    limit_set = bootstrap_limit_set()
    assert limit_set.basis_uris
    assert not any("result" in uri for uri in limit_set.basis_uris)


def test_limit_with_no_source_is_load_refused() -> None:
    bad = dataclasses.replace(_good_limit(), source="")
    with pytest.raises(DerivationBasisError):
        bad.validate()


def test_limit_with_no_formula_is_load_refused() -> None:
    bad = dataclasses.replace(_good_limit(), formula="")
    with pytest.raises(DerivationBasisError):
        bad.validate()


def test_limit_with_non_positive_gear_ratio_is_load_refused() -> None:
    bad = dataclasses.replace(_good_limit(), gear_ratio=0.0)
    with pytest.raises(DerivationBasisError):
        bad.validate()


def test_limit_exceeding_motor_output_vmax_is_load_refused() -> None:
    # A joint ceiling cannot be faster than the motor that drives it.
    bad = dataclasses.replace(_good_limit(), value_rad_s=50.0, motor_vmax_rad_s=45.0)
    with pytest.raises(DerivationBasisError):
        bad.validate()


def test_set_with_empty_basis_uris_is_load_refused() -> None:
    with pytest.raises(DerivationBasisError):
        LimitSet(
            version=1, provenance="bootstrap", basis_uris=(), limits=(_good_limit(),)
        ).validate()


def test_set_with_version_below_one_is_load_refused() -> None:
    bad = LimitSet(version=0, provenance="bootstrap", basis_uris=("s",), limits=(_good_limit(),))
    with pytest.raises(DerivationBasisError):
        bad.validate()


def test_set_with_one_unbacked_joint_is_load_refused() -> None:
    unbacked = dataclasses.replace(_good_limit(), joint_index=1, formula="")
    bad = LimitSet(
        version=1, provenance="bootstrap", basis_uris=("s",), limits=(_good_limit(), unbacked)
    )
    with pytest.raises(DerivationBasisError):
        bad.validate()
