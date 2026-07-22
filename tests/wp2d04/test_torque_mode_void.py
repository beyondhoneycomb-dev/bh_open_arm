"""Acceptance ④ — LeRobot's joint_limits position clip is void in torque mode.

The clip acts on the `.pos` command only; Freedrive drives `tau`, so the clip is void and the
repulsion torque is what holds the limit. The proof: at an angle near but within a limit the
modeled position clip is the identity — no restoring action — while the repulsion torque there
is nonzero, on a channel the clip does not touch.
"""

from __future__ import annotations

import pytest

pytest.importorskip("mujoco")

from backend.freedrive_walls import (
    modeled_lerobot_position_clip,
    position_clip_is_void,
)
from contracts.units.tags import Nm
from tests.wp2d04._fixtures import SYNTHETIC_UPPER_RAD, synthetic_repulsion

_BAND_RAD = 0.0873


def test_position_clip_is_identity_within_limits() -> None:
    """Within the limits the modeled clip changes nothing, so it exerts no restoring action."""
    near = SYNTHETIC_UPPER_RAD[0] - _BAND_RAD / 2.0
    assert modeled_lerobot_position_clip(near, -1.0, 1.0) == near
    assert position_clip_is_void(near, -1.0, 1.0)


def test_position_clip_only_bites_past_a_limit() -> None:
    """The clip clamps an over-limit position to the bound — the only thing it ever does."""
    assert modeled_lerobot_position_clip(1.5, -1.0, 1.0) == 1.0
    assert not position_clip_is_void(1.5, -1.0, 1.0)


def test_torque_wall_acts_where_position_clip_is_void() -> None:
    """At a near-limit in-bounds angle the clip is void yet the repulsion torque is nonzero."""
    rep = synthetic_repulsion(fraction=0.5, band_rad=_BAND_RAD)
    q = [0.0] * rep.count
    q[0] = SYNTHETIC_UPPER_RAD[0] - _BAND_RAD / 2.0
    assert position_clip_is_void(q[0], -1.0, 1.0)  # position clip does nothing here
    torque = rep.repulsion_torque(q)
    assert torque[0].value != 0.0  # the torque wall does


def test_repulsion_output_is_on_the_torque_channel() -> None:
    """The wall's output is an Nm torque, not a position — the channel the clip cannot reach."""
    rep = synthetic_repulsion()
    torque = rep.repulsion_torque([0.0] * rep.count)
    assert all(isinstance(entry, Nm) for entry in torque)
