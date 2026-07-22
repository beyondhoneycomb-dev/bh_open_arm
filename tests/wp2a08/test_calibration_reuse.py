"""`GripperEndpointCapture.from_calibration` reads the CTR-CAL endpoints (no re-capture).

The per-arm zero calibration (`OpenArmCalibration`, CTR-CAL@v1) already persists the
gripper open/close endpoint rads. This WP reads them through the bridge rather than
maintaining a second endpoint source, so the norm-map anchors and the calibration can
never disagree.
"""

from __future__ import annotations

import math

from backend.calibration.schema import MOTOR_COUNT, OpenArmCalibration
from backend.gripper_endpoint.schema import GripperEndpointCapture


def _calibration(side: str) -> OpenArmCalibration:
    """Build a minimal valid calibration carrying gripper endpoints for one side."""
    return OpenArmCalibration(
        robot_type="openarm_follower",
        robot_id=f"{side}0",
        side=side,
        motor_zero_raw=[0.0] * MOTOR_COUNT,
        urdf_zero_offset=[0.0] * MOTOR_COUNT,
        gripper_open_rad=0.0,
        gripper_close_rad=-math.pi / 2,
        gripper_open_captured=True,
        gripper_close_captured=True,
    )


def test_bridge_reads_calibration_endpoints() -> None:
    """The capture takes its side and endpoint rads straight from the calibration."""
    calibration = _calibration("right")
    capture = GripperEndpointCapture.from_calibration(calibration)

    assert capture.side == "right"
    assert capture.open_rad == calibration.gripper_open_rad
    assert capture.close_rad == calibration.gripper_close_rad
    assert capture.open_captured is True
    assert capture.close_captured is True


def test_bridged_capture_is_mappable() -> None:
    """A capture built from a real calibration defines a valid norm map."""
    capture = GripperEndpointCapture.from_calibration(_calibration("left"))
    capture.require_mappable()  # does not raise
