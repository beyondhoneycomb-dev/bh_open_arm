"""Acceptance ① — the dummy returns the real schema, field diff 0.

`get_observation()` must return exactly the frozen real-follower feature set
(WP-0A-02): every one of the 48 tagged channels plus the CAN drop-counter meta, no
field missing and no dummy-only field added. The type of each value must match the
schema's declared scalar type. An obs-missing fault, by contrast, must produce a
non-empty diff — the proof the diff check is not vacuous.
"""

from __future__ import annotations

from pathlib import Path

from packages.lerobot_robot_openarm_dummy import (
    REAL_OBSERVATION_FEATURES,
    DummyOpenArmRobot,
    DummyRobotConfig,
    frame_matches_schema,
    observation_field_diff,
)


def _connected_dummy(workdir: Path) -> DummyOpenArmRobot:
    """Build and connect a dummy follower with calibration parked in workdir."""
    robot = DummyOpenArmRobot(DummyRobotConfig(id="follower", calibration_dir=workdir))
    robot.connect()
    return robot


def test_observation_field_diff_is_zero(tmp_path: Path) -> None:
    """The healthy dummy frame carries exactly the real schema's fields."""
    robot = _connected_dummy(tmp_path)
    frame = robot.get_observation()
    missing, extra = observation_field_diff(frame)
    assert missing == frozenset()
    assert extra == frozenset()


def test_observation_has_no_dummy_only_field(tmp_path: Path) -> None:
    """No field beyond the real schema appears — zero dummy-only fields."""
    robot = _connected_dummy(tmp_path)
    frame = robot.get_observation()
    assert set(frame) == set(REAL_OBSERVATION_FEATURES)


def test_observation_value_types_match_schema(tmp_path: Path) -> None:
    """Every returned value is an instance of the schema's declared scalar type."""
    robot = _connected_dummy(tmp_path)
    frame = robot.get_observation()
    assert frame_matches_schema(frame)
    for name, declared in REAL_OBSERVATION_FEATURES.items():
        assert isinstance(frame[name], declared), name


def test_obs_missing_fault_makes_diff_nonzero(tmp_path: Path) -> None:
    """A dropped channel is detected as a schema mismatch (the diff check bites)."""
    robot = _connected_dummy(tmp_path)
    robot.fault.drop_channels = ("left_joint_1.pos",)
    frame = robot.get_observation()
    missing, extra = observation_field_diff(frame)
    assert "left_joint_1.pos" in missing
    assert extra == frozenset()
    assert not frame_matches_schema(frame)
