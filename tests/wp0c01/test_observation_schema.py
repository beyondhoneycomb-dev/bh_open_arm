"""Acceptance ⑥ -- get_observation() passes the WP-0A-02 (CTR-ACT@v1) schema.

The returned observation must match the frozen contract: exactly the 48 named
`observation.state` channels plus the CAN drop-counter meta, floats for the
physical channels and an int for the counter, and dimension 48. The frozen schema
itself must validate, tying the runtime observation to the WP-0A-02 declaration.
The per-index units are checked at the boundary: a known radian joint state reads
back as the matching degrees.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

pytest.importorskip("mujoco")
pytest.importorskip("lerobot")

from contracts.action.observation import (  # noqa: E402
    BIMANUAL_OBSERVATION_DIM,
    DROP_COUNTER_META,
    raw_observation_dim,
)
from contracts.action.schema import load_schema, validate_schema  # noqa: E402
from packages.lerobot_robot_openarm_mujoco import (  # noqa: E402
    BiOpenArmMujoco,
    BiOpenArmMujocoConfig,
)


def _connected_backend(calibration_dir: Path) -> BiOpenArmMujoco:
    backend = BiOpenArmMujoco(BiOpenArmMujocoConfig(id="wp0c01", calibration_dir=calibration_dir))
    backend.connect()
    return backend


def test_frozen_ctr_act_schema_validates() -> None:
    assert validate_schema(load_schema()) == ()


def test_observation_keys_match_observation_features(tmp_path: Path) -> None:
    backend = _connected_backend(tmp_path)
    observation = backend.get_observation()
    assert set(observation) == set(backend.observation_features)


def test_observation_has_48_channels_plus_drop_meta(tmp_path: Path) -> None:
    backend = _connected_backend(tmp_path)
    observation = backend.get_observation()

    assert DROP_COUNTER_META in observation
    physical = {name: value for name, value in observation.items() if name != DROP_COUNTER_META}
    assert len(physical) == BIMANUAL_OBSERVATION_DIM == raw_observation_dim()


def test_observation_value_types_match_the_schema(tmp_path: Path) -> None:
    backend = _connected_backend(tmp_path)
    observation = backend.get_observation()

    assert isinstance(observation[DROP_COUNTER_META], int)
    for name, value in observation.items():
        if name != DROP_COUNTER_META:
            assert isinstance(value, float), f"{name} is not a float"


def test_observation_positions_carry_degrees_from_radian_state(tmp_path: Path) -> None:
    backend = _connected_backend(tmp_path)
    backend._scene.set_joint_positions({"left_joint_2": -0.7, "right_gripper": 0.2})
    observation = backend.get_observation()

    assert observation["left_joint_2.pos"] == pytest.approx(math.degrees(-0.7))
    assert observation["right_gripper.pos"] == pytest.approx(math.degrees(0.2))
