"""RUNS ① (CG-3B-09a) — clutch release discards the reference; re-grip delta is zero.

`FR-TEL-031` / `05` §4.2 forbidden transition 7: at the instant the clutch re-engages
the follower delta must start at exactly zero, so re-gripping never snaps the arm. The
invariant is enforced here both at the component level (`ClutchGate` + `DeltaScaler`) and
through the coordinator consuming the frozen VR sample.
"""

from __future__ import annotations

import numpy as np

from backend.teleop.clutch import ClutchGate, DeltaScaler, TeleopPoseConditioner
from contracts.teleop import TeleopValidity
from tests.wp3b09._support import IDENTITY_QUAT, make_frame

_ENGAGE_GRIP = 0.95
_RELEASE_GRIP = 0.0
_HALF_TURN_Y = (0.0, np.sin(np.pi / 4), 0.0, np.cos(np.pi / 4))


def test_release_discards_reference() -> None:
    """A grip drop below threshold clears the latched reference entirely."""
    gate = ClutchGate()
    ee_position = np.array([1.0, 2.0, 3.0])
    controller = np.array([0.5, 0.5, 0.5])

    engaged = gate.update(_ENGAGE_GRIP, controller, IDENTITY_QUAT, ee_position, IDENTITY_QUAT)
    assert engaged.just_engaged is True
    assert gate.reference is not None

    released = gate.update(_RELEASE_GRIP, controller, IDENTITY_QUAT, ee_position, IDENTITY_QUAT)
    assert released.just_released is True
    assert gate.is_engaged is False
    assert gate.reference is None


def test_regrip_at_new_pose_starts_delta_zero() -> None:
    """Re-gripping re-captures the reference, so the immediate target equals the EE pose."""
    gate = ClutchGate()
    scaler = DeltaScaler(position_scale=0.8, rotation_scale=1.0)

    # First grip at controller A over EE pose E0, then follow to B (a real, non-zero delta).
    controller_a = np.array([0.0, 0.0, 0.0])
    ee_0 = np.array([0.10, 0.20, 0.30])
    gate.update(_ENGAGE_GRIP, controller_a, IDENTITY_QUAT, ee_0, IDENTITY_QUAT)
    controller_b = np.array([0.05, -0.02, 0.03])
    followed = scaler.target(gate.reference, controller_b, IDENTITY_QUAT)
    assert not np.allclose(followed.position, ee_0)  # following produced a real delta

    # Release, drift the controller far away, then re-grip over a moved EE pose E1.
    gate.update(_RELEASE_GRIP, controller_b, IDENTITY_QUAT, ee_0, IDENTITY_QUAT)
    controller_c = np.array([0.90, -0.70, 0.40])
    ee_1 = np.array([-0.15, 0.05, 0.25])
    regrip = gate.update(_ENGAGE_GRIP, controller_c, _HALF_TURN_Y, ee_1, _HALF_TURN_Y)
    assert regrip.just_engaged is True

    # With the controller still at C (the just-captured reference), the delta is zero:
    # target == the reference EE pose, not a jump relative to the pre-release reference.
    target = scaler.target(gate.reference, controller_c, _HALF_TURN_Y)
    assert np.allclose(target.position, ee_1)
    assert np.allclose(target.quaternion, _HALF_TURN_Y)


def test_conditioner_regrip_target_equals_ee_pose() -> None:
    """Through the coordinator, the re-grip tick reports a captured reference and zero delta."""
    conditioner = TeleopPoseConditioner()
    ee_position = np.array([0.2, -0.1, 0.4])
    ee_quaternion = np.array(IDENTITY_QUAT)

    # Engage, follow, release across three ticks.
    conditioner.process(
        make_frame(_ENGAGE_GRIP, TeleopValidity.OK, (0.0, 0.0, 0.0), IDENTITY_QUAT, 0),
        "right",
        ee_position,
        ee_quaternion,
    )
    conditioner.process(
        make_frame(_ENGAGE_GRIP, TeleopValidity.OK, (0.1, 0.1, 0.0), IDENTITY_QUAT, 16_000_000),
        "right",
        ee_position,
        ee_quaternion,
    )
    conditioner.process(
        make_frame(_RELEASE_GRIP, TeleopValidity.OK, (0.1, 0.1, 0.0), IDENTITY_QUAT, 32_000_000),
        "right",
        ee_position,
        ee_quaternion,
    )

    # Re-grip over a new EE pose and a drifted controller: the first target is that EE pose.
    new_ee = np.array([0.55, 0.33, -0.12])
    result = conditioner.process(
        make_frame(_ENGAGE_GRIP, TeleopValidity.OK, (0.8, -0.6, 0.2), IDENTITY_QUAT, 48_000_000),
        "right",
        new_ee,
        ee_quaternion,
    )
    assert result.reference_captured is True
    assert result.engaged is True
    assert result.target is not None
    assert np.allclose(result.target.position, new_ee)
