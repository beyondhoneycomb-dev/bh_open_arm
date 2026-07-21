"""Acceptance ⑥ (FR-SIM-133 inert-then-detect) and ⑦ (the ±40/±27/±7 Nm limits)."""

from __future__ import annotations

from contracts.units.tags import Nm
from sim.dryrun.checks.torque import check_torque_limits
from sim.dryrun.limits import arm_motor_keys, torque_limits_nm
from sim.dryrun.torque_probe import PROBE_MOTOR_KEY, demonstrate


def test_torque_limits_are_the_confirmed_nm_table() -> None:
    """⑦ Limits are ±40 (J1/J2), ±27 (J3/J4), ±7 (J5-J7) Nm, as Nm tags."""
    limits = torque_limits_nm()
    for side in ("left", "right"):
        assert limits[f"{side}_joint_1"] == Nm(40.0)
        assert limits[f"{side}_joint_2"] == Nm(40.0)
        assert limits[f"{side}_joint_3"] == Nm(27.0)
        assert limits[f"{side}_joint_4"] == Nm(27.0)
        assert limits[f"{side}_joint_5"] == Nm(7.0)
        assert limits[f"{side}_joint_6"] == Nm(7.0)
        assert limits[f"{side}_joint_7"] == Nm(7.0)
    assert all(isinstance(value, Nm) for value in limits.values())


def test_torque_table_excludes_the_gripper() -> None:
    """⑦ The gripper carries no confirmed torque canon (Q2), so it is absent."""
    limits = torque_limits_nm()
    assert set(limits) == set(arm_motor_keys())
    assert not any("gripper" in key for key in limits)


def test_implicit_actuator_reading_is_inert_then_measured_detects() -> None:
    """⑥ The clamped actuator reading silently passes; inverse dynamics catches it."""
    probe = demonstrate(Nm(7.0))
    limits = {PROBE_MOTOR_KEY: Nm(7.0)}

    # The clamped actuator force sits at the bound and the naive check passes.
    assert abs(probe.inert_effort_nm.value) <= 7.0
    inert_violations = check_torque_limits({PROBE_MOTOR_KEY: probe.inert_effort_nm}, limits, 0.0)
    assert inert_violations == ()

    # The measured (inverse-dynamics) torque exceeds the bound and is detected.
    assert abs(probe.measured_effort_nm.value) > 7.0
    measured_violations = check_torque_limits(
        {PROBE_MOTOR_KEY: probe.measured_effort_nm}, limits, 0.0
    )
    assert len(measured_violations) == 1
    assert measured_violations[0].overage > 0.0
