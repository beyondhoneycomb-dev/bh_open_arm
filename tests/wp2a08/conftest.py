"""Shared builders for the WP-2A-08 acceptance tests.

The canonical numbers are FR-TEL-059's: the right gripper limit is `[-65deg, 0]` and
the mirror-correct left is `[0, +65deg]`. Endpoint captures use the mechanical stops
`0 -> -pi/2` (right) and `0 -> +pi/2` (left): open at norm 0, close at norm 1.
"""

from __future__ import annotations

import math

import pytest

from backend.gripper_endpoint.schema import (
    GripperEndpointCapture,
    GripperLimits,
    GripperMirrorRecord,
)

RIGHT_LO_RAD = math.radians(-65.0)
RIGHT_HI_RAD = 0.0
# The sign-mirror of the right limits: (-hi_right, -lo_right).
LEFT_LO_RAD = -RIGHT_HI_RAD
LEFT_HI_RAD = -RIGHT_LO_RAD

RIGHT_OPEN_RAD = 0.0
RIGHT_CLOSE_RAD = -math.pi / 2
LEFT_OPEN_RAD = 0.0
LEFT_CLOSE_RAD = math.pi / 2

REQUESTED_SPEED_RAD_S = 50.0
FORCE_PU = 0.4


def make_right_capture() -> GripperEndpointCapture:
    """Return a valid right-side endpoint capture."""
    return GripperEndpointCapture("right", RIGHT_OPEN_RAD, RIGHT_CLOSE_RAD, True, True)


def make_left_capture() -> GripperEndpointCapture:
    """Return a valid left-side endpoint capture."""
    return GripperEndpointCapture("left", LEFT_OPEN_RAD, LEFT_CLOSE_RAD, True, True)


def make_record(
    left_lo: float = LEFT_LO_RAD,
    left_hi: float = LEFT_HI_RAD,
    speed_rad_s: float = REQUESTED_SPEED_RAD_S,
    torque_pu: float = FORCE_PU,
) -> GripperMirrorRecord:
    """Build a mirror record, defaulting to the mirror-correct left limits.

    Overriding `left_lo`/`left_hi` yields an un-mirrored config the record refuses.
    """
    return GripperMirrorRecord(
        right_capture=make_right_capture(),
        left_capture=make_left_capture(),
        right_limits=GripperLimits("right", RIGHT_LO_RAD, RIGHT_HI_RAD),
        left_limits=GripperLimits("left", left_lo, left_hi),
        speed_rad_s=speed_rad_s,
        torque_pu=torque_pu,
    )


@pytest.fixture
def valid_record() -> GripperMirrorRecord:
    """A valid, sign-mirrored gripper record."""
    return make_record()
