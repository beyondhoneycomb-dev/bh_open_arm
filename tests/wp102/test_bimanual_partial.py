"""Acceptance ⑫: bimanual partial connect leaves no orphaned arm (01 §4.2 T1).

The stock left→right sequential connect leaves the left arm connected if the right
fails. WP-1-02's `connect_readonly` tears the left arm down and raises instead, so a
half-connected pair never runs and the surviving connection is never orphaned.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from contracts.plugin.config import Side
from packages.lerobot_robot_openarm.config_oa import (
    BiOaOpenArmFollowerConfig,
    OaOpenArmFollowerConfig,
)
from packages.lerobot_robot_openarm.openarm_follower_oa import (
    BiOaOpenArmFollower,
    OaOpenArmFollower,
    PartialConnectionError,
)
from tests.wp102.conftest import FakeDamiaoBus


def _bimanual(tmp_path: Path, right_connect_fails: bool) -> BiOaOpenArmFollower:
    """Build a bimanual follower whose right arm optionally fails to connect."""
    config = BiOaOpenArmFollowerConfig(id="bi", calibration_dir=tmp_path)
    left = OaOpenArmFollower(
        OaOpenArmFollowerConfig(side=Side.LEFT, id="bi_left", calibration_dir=tmp_path),
        bus=FakeDamiaoBus(),
    )
    right = OaOpenArmFollower(
        OaOpenArmFollowerConfig(side=Side.RIGHT, id="bi_right", calibration_dir=tmp_path),
        bus=FakeDamiaoBus(connect_fails=right_connect_fails),
    )
    return BiOaOpenArmFollower(config, left=left, right=right)


def test_partial_connect_tears_down_the_left_arm(tmp_path: Path) -> None:
    """Left ok / right fail: the left arm is disconnected and the error is explicit (⑫)."""
    bimanual = _bimanual(tmp_path, right_connect_fails=True)
    with pytest.raises(PartialConnectionError):
        bimanual.connect_readonly()
    assert bimanual.left_arm.is_connected is False, "left arm left orphaned"
    assert bimanual.right_arm.is_connected is False
    assert bimanual.is_connected is False


def test_both_arms_connect_when_healthy(tmp_path: Path) -> None:
    """Both arms healthy: the bimanual comes up torque-OFF with both connected."""
    bimanual = _bimanual(tmp_path, right_connect_fails=False)
    bimanual.connect_readonly()
    assert bimanual.is_connected is True
    assert bimanual.is_torque_enabled is False
