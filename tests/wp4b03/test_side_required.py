"""CG-4B-03c — an unspecified side does not start inference (+/-5 degree lock).

FR-INF-037: with `--robot.side` unset, LeRobot leaves `joint_limits` at its +/-5
degree default and the arm is effectively inert. The preflight refuses the load so
the failure surfaces as a refusal at load time, not as a mysteriously motionless arm
at run time.
"""

from __future__ import annotations

from backend.inference.load_preflight import (
    LoadPreflight,
    RefusalCode,
    RobotProfile,
)
from contracts.plugin.config import Side
from tests.wp4b03.support import matching_checkpoint


def test_side_unspecified_is_refused() -> None:
    """CG-4B-03c: single-arm side=None -> inference does not start."""
    robot = RobotProfile.single(side=None, use_velocity_and_torque=False)
    checkpoint = matching_checkpoint(robot, policy_id="act")

    verdict = LoadPreflight().check(checkpoint, robot)

    assert not verdict.allowed
    assert any(r.code is RefusalCode.SIDE_UNSPECIFIED for r in verdict.refusals)


def test_side_specified_is_allowed() -> None:
    """A specified side clears the side gate (the check is not vacuous)."""
    robot = RobotProfile.single(side=Side.RIGHT, use_velocity_and_torque=False)
    checkpoint = matching_checkpoint(robot, policy_id="act")

    verdict = LoadPreflight().check(checkpoint, robot)

    assert verdict.allowed
    assert all(r.code is not RefusalCode.SIDE_UNSPECIFIED for r in verdict.refusals)
