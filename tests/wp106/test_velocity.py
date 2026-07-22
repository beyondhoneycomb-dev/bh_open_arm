"""Acceptance ⑨-c ⑨-d ⑩: three-way derivation, register-never-canon, self-approval, default-on.

The load-bearing arithmetic fact: for the DM4340 joints the register V_MAX (8 rad/s) exceeds
both the catalogue (5.45) and the URDF (5.4454), so the canon resolves away from the register.
The register is never the minimum on any joint — hardware cannot be the source of its own
safety limit.
"""

from __future__ import annotations

import pytest

from backend.safety_bringup import (
    DerivationSelfApprovalError,
    VelocitySource,
    assert_derivation_basis_not_self,
    assert_register_never_canon,
    assert_velocity_limit_active_by_default,
    bootstrap_limiter_rad_s,
    physical_canon_rad_s,
    three_way_table,
    velocity_limiter_default,
)
from backend.safety_bringup.constants import VELOCITY_CAP_RAD_S


def test_three_way_table_has_seven_rows() -> None:
    assert len(three_way_table()) == 7


def test_dm4340_canon_is_urdf_not_register() -> None:
    # ⑨-c: the DM4340 joints (J3/J4, index 2/3) resolve to URDF 5.4454, not register 8.
    table = three_way_table()
    for index in (2, 3):
        row = table[index]
        assert row.register_vmax_rad_s == 8.0
        assert row.canon_source is VelocitySource.URDF
        assert row.canon_rad_s == pytest.approx(5.4454)
        assert row.canon_rad_s < row.register_vmax_rad_s


def test_register_is_never_canon_on_any_joint() -> None:
    # ⑨-c: hardware cannot be the source of its own safety limit.
    table = three_way_table()
    for row in table:
        assert not row.register_is_canon
    assert_register_never_canon(table)


def test_register_as_canon_is_refused() -> None:
    # A table where a joint's canon is the register must be refused (the forbidden case).
    from dataclasses import replace

    table = list(three_way_table())
    table[0] = replace(
        table[0],
        canon_rad_s=table[0].register_vmax_rad_s,
        canon_source=VelocitySource.REGISTER,
    )
    with pytest.raises(DerivationSelfApprovalError, match="own safety limit"):
        assert_register_never_canon(tuple(table))


def test_physical_canon_is_three_way_minimum() -> None:
    assert physical_canon_rad_s() == pytest.approx(
        (16.755, 16.755, 5.4454, 5.4454, 20.944, 20.944, 20.944)
    )


def test_bootstrap_limiter_overlays_the_velocity_cap() -> None:
    # ③ (§5.6.0 ②): the bootstrap limiter is the minimum of the physical canon and the cap.
    limiter = bootstrap_limiter_rad_s()
    canon = physical_canon_rad_s()
    for value, canon_value, cap in zip(limiter, canon, VELOCITY_CAP_RAD_S, strict=True):
        assert value == pytest.approx(min(canon_value, cap))
    # For this asset set the §2.5 cap is the tightest source everywhere.
    assert limiter == pytest.approx(VELOCITY_CAP_RAD_S)


def test_bootstrap_limiter_never_exceeds_physical_canon() -> None:
    for value, canon_value in zip(bootstrap_limiter_rad_s(), physical_canon_rad_s(), strict=True):
        assert value <= canon_value


def test_derivation_basis_pointing_at_own_result_is_refused() -> None:
    # ⑨-d: a basis URI under the gate's own result record is self-approval => FAIL_BLOCKING.
    result = "registry/build/evidence/CG-1-06i/"
    with pytest.raises(DerivationSelfApprovalError, match="self-approval"):
        assert_derivation_basis_not_self((result + "table.json",), result)


def test_empty_derivation_basis_is_refused() -> None:
    with pytest.raises(DerivationSelfApprovalError, match="no basis"):
        assert_derivation_basis_not_self((), "registry/build/evidence/CG-1-06i/")


def test_physical_source_basis_is_accepted() -> None:
    assert_derivation_basis_not_self(
        ("docs/spec/03-모터-설정.md#trap-2", "backend/can/rid/motor_limits.py"),
        "registry/build/evidence/CG-1-06i/",
    )


def test_velocity_limiter_is_active_by_default() -> None:
    # ⑩: the arm velocity limiter is active by default (we flip the upstream default-off).
    default = velocity_limiter_default()
    assert default.active is True
    assert default.limits_rad_s == bootstrap_limiter_rad_s()
    assert_velocity_limit_active_by_default(default)


def test_inactive_velocity_limiter_default_is_refused() -> None:
    from dataclasses import replace

    inactive = replace(velocity_limiter_default(), active=False)
    with pytest.raises(ValueError, match="not active by default"):
        assert_velocity_limit_active_by_default(inactive)
