"""The dataset the embed produces obeys `CTR-REC@v1` and LeRobot's own guards.

- `action` stays position-only: a frame samples its `action` vector from the
  `.pos` channel names alone, so a `.vel`/`.torque` value in the teleop action can
  never reach an `action` dimension, and the produced `info.json` carries a
  position-only `action`.
- the fps guard blocks a loop whose rate disagrees with the dataset's (⑦).
- an `eval_` name is refused (⑥), and the `repo_id` is stamped so each session is
  unique and the stamped name is what creation returns (⑤).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from backend.recorder.embed import (
    RecorderFpsMismatchError,
    RecorderNameError,
    RecordEvents,
    build_record_frame,
    create_record_dataset,
    frame_schema,
    record_loop,
    reject_eval_name,
    stamp_repo_id,
)
from contracts.recorder import (
    ACTION_KEY,
    TORQUE_SUFFIX,
    VELOCITY_SUFFIX,
    RecorderConfig,
    action_dim,
    action_names,
    observation_state_names,
)

from ._support import DummyRobotAdapter, FakeDataset, RampTeleop

FPS = 30
_CONFIG = RecorderConfig(bimanual=True, use_velocity_and_torque=True)


def test_action_frame_drops_velocity_and_torque() -> None:
    """A teleop action carrying .vel/.torque keys still yields a position-only action."""
    schema = frame_schema(_CONFIG)
    pos_action = dict.fromkeys(action_names(_CONFIG.bimanual), 1.0)
    # An out-of-contract action that also carries vel/torque channels for each motor.
    poisoned = dict(pos_action)
    for name in action_names(_CONFIG.bimanual):
        motor = name.rsplit(".", 1)[0]
        poisoned[f"{motor}{VELOCITY_SUFFIX}"] = 9.0
        poisoned[f"{motor}{TORQUE_SUFFIX}"] = 9.0
    observation = dict.fromkeys(
        observation_state_names(_CONFIG.bimanual, _CONFIG.use_velocity_and_torque), 0.0
    )

    frame = build_record_frame(poisoned, observation, "grab", schema)

    action_vector = frame[ACTION_KEY]
    assert action_vector.shape == (action_dim(_CONFIG.bimanual),)
    # Every sampled value is the position 1.0 — no 9.0 velocity/torque leaked in.
    assert set(action_vector.tolist()) == {1.0}


def test_produced_info_json_action_is_position_only(tmp_path: Path) -> None:
    """The created dataset's info.json action carries only .pos names, at the frozen width."""
    dataset, _ = create_record_dataset("synthetic/oa", FPS, _CONFIG, tmp_path / "ds")
    action_feature = dataset.meta.info.features[ACTION_KEY]
    names = action_feature["names"]
    assert len(names) == action_dim(_CONFIG.bimanual)
    assert not any(name.endswith((VELOCITY_SUFFIX, TORQUE_SUFFIX)) for name in names)
    dataset.finalize()


def test_fps_mismatch_blocks_recording() -> None:
    """A loop fps that disagrees with the dataset fps is refused before any frame."""
    schema = frame_schema(_CONFIG)
    dataset = FakeDataset(fps=25)
    with pytest.raises(RecorderFpsMismatchError):
        record_loop(
            robot=DummyRobotAdapter(True, True),
            teleop=RampTeleop(True),
            events=RecordEvents(),
            fps=FPS,
            max_steps=1,
            single_task="grab",
            schema=schema,
            dataset=dataset,
        )


def test_eval_name_is_refused() -> None:
    """An eval_ dataset name is reserved for policy evaluation, not recording."""
    reject_eval_name("account/grab_cube")  # a normal name is accepted
    with pytest.raises(RecorderNameError):
        reject_eval_name("account/eval_grab_cube")
    with pytest.raises(RecorderNameError):
        reject_eval_name("eval_grab_cube")


def test_create_refuses_eval_name(tmp_path: Path) -> None:
    """Dataset creation refuses an eval_ name up front, before any write."""
    with pytest.raises(RecorderNameError):
        create_record_dataset("account/eval_grab", FPS, _CONFIG, tmp_path)


def test_repo_id_is_stamped() -> None:
    """Stamping appends a date-time so each session's name is unique."""
    moment = datetime(2026, 7, 23, 6, 3, 8)
    assert stamp_repo_id("account/grab", moment) == "account/grab_20260723_060308"
    assert stamp_repo_id("", moment) == ""


def test_created_dataset_uses_the_stamped_name(tmp_path: Path) -> None:
    """Creation returns the stamped name and the dataset is created under it."""
    moment = datetime(2026, 7, 23, 6, 3, 8)
    dataset, stamped = create_record_dataset("synthetic/oa", FPS, _CONFIG, tmp_path / "ds", moment)
    assert stamped == "synthetic/oa_20260723_060308"
    assert dataset.repo_id == stamped
    dataset.finalize()
