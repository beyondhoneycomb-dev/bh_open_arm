"""The conditioner consumes the WP-3B-07/08 `PoseSource` interface, never re-implements it.

`02b` §5.0b ("do not duplicate"): WP-3B-09 imports the source-agnostic `PoseSource` /
`VrFrame` from `backend.teleop.vr_udp` and conditions its frames. This exercises that
consumption path and confirms the no-frame-yet case returns None rather than blocking.
"""

from __future__ import annotations

import numpy as np

from backend.teleop.clutch import TeleopPoseConditioner
from contracts.teleop import TeleopValidity
from tests.wp3b09._support import IDENTITY_QUAT, StaticPoseSource, make_frame

_ENGAGE_GRIP = 0.95
_EE = np.array([0.4, -0.2, 0.1])
_EE_QUAT = np.array(IDENTITY_QUAT)


def test_process_source_returns_none_before_any_frame() -> None:
    """With no frame available the conditioner yields None (non-blocking read)."""
    conditioner = TeleopPoseConditioner()
    source = StaticPoseSource(None)
    assert conditioner.process_source(source, "right", _EE, _EE_QUAT) is None


def test_process_source_conditions_the_latest_frame() -> None:
    """A frame from the source is conditioned; first engage captures the reference."""
    conditioner = TeleopPoseConditioner()
    frame = make_frame(_ENGAGE_GRIP, TeleopValidity.OK, (0.0, 0.0, 0.0), IDENTITY_QUAT, 0)
    source = StaticPoseSource(frame)

    result = conditioner.process_source(source, "right", _EE, _EE_QUAT)
    assert result is not None
    assert result.engaged is True
    assert result.reference_captured is True
    assert result.target is not None
    assert np.allclose(result.target.position, _EE)  # delta zero at capture


def test_invalid_arm_withholds_the_pose() -> None:
    """An INVALID arm (no `world_pose`) is not published and captures nothing."""
    conditioner = TeleopPoseConditioner()
    frame = make_frame(_ENGAGE_GRIP, TeleopValidity.INVALID, (0.0, 0.0, 0.0), IDENTITY_QUAT, 0)
    source = StaticPoseSource(frame)

    result = conditioner.process_source(source, "right", _EE, _EE_QUAT)
    assert result is not None
    assert result.published is False
    assert result.target is None
