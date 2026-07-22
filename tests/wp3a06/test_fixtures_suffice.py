"""The fixtures suffice for a 3B unit+integration test with no hardware (WP-3A-06 ③).

`02b` §5.2 WP-3A-06 ③: the four world stand-ins — VR pose stream, dummy robot,
synthetic dataset, and (via the dataset) the synthetic camera — must let a 3B test
run standalone. These tests exercise each on its own and then together: a dataset
whose feature set is exactly the frozen `CTR-REC@v1` closed set and whose camera slot
round-trips across all four consumer contracts, which is the join the barrier rests on.
"""

from __future__ import annotations

import pytest

from contracts.fixtures import (
    DummyRobot,
    SyntheticVrPoseStream,
    build_synthetic_dataset,
    timestamp_roles,
    validity_wire_values,
)
from contracts.prim import (
    FrameType,
    slot_from_capture_ts_column,
    slot_from_image_key,
    slot_from_ws_tag,
)
from contracts.recorder import RecorderConfig, allowed_info_keys
from contracts.teleop import TeleopValidity

# --- Synthetic VR pose stream -------------------------------------------------


def test_vr_stream_is_deterministic() -> None:
    """The same stream config emits identical samples on a rerun."""
    a = SyntheticVrPoseStream().samples(8)
    b = SyntheticVrPoseStream().samples(8)
    assert a == b


def test_vr_stream_preserves_both_timestamps_on_distinct_clocks() -> None:
    """Each sample keeps a source (client) time and a receive (server) instant."""
    sample = SyntheticVrPoseStream(start_source_ts=1.0, start_receive_mono_ns=10_000).sample(1)
    assert sample.teleop_sample.source_ts > 1.0
    assert sample.teleop_sample.receive_mono_ns > 10_000
    assert timestamp_roles() == ("client", "server")


def test_vr_stream_three_level_validity_controls_publication() -> None:
    """STALE still publishes; INVALID is withheld — the wire values are the frozen enum."""
    stream = SyntheticVrPoseStream(stale_indices=frozenset({2}), invalid_indices=frozenset({4}))
    samples = stream.samples(6)
    assert samples[2].validity == TeleopValidity.STALE and samples[2].is_publishable
    assert samples[4].validity == TeleopValidity.INVALID and not samples[4].is_publishable
    published = stream.published(6)
    assert len(published) == 5 and all(sample.is_publishable for sample in published)
    assert validity_wire_values() == [0, 1, 2]


def test_vr_stream_rejects_a_double_marked_index() -> None:
    """A sample is one validity: an index cannot be both STALE and INVALID."""
    with pytest.raises(ValueError):
        SyntheticVrPoseStream(stale_indices=frozenset({3}), invalid_indices=frozenset({3}))


# --- Dummy robot --------------------------------------------------------------


def test_dummy_robot_returns_a_48_dim_observation() -> None:
    """A bimanual velocity+torque robot observes a 48-wide interleaved state."""
    robot = DummyRobot(bimanual=True, use_velocity_and_torque=True)
    observation = robot.step(robot.zero_action())
    assert len(observation["observation.state"]) == 48
    assert robot.action_dim() == 16


def test_dummy_robot_rejects_a_torque_action_channel() -> None:
    """A .torque key in the action is the FAIL_BLOCKING dimension the robot refuses."""
    robot = DummyRobot(bimanual=True, use_velocity_and_torque=True)
    poisoned = robot.zero_action()
    first_motor = robot.action_names()[0].removesuffix(".pos")
    poisoned[f"{first_motor}.torque"] = 1.0
    with pytest.raises(ValueError):
        robot.step(poisoned)


def test_dummy_robot_motion_is_deterministic() -> None:
    """The same command history produces the same observation vector."""
    a = DummyRobot(bimanual=True, use_velocity_and_torque=True)
    b = DummyRobot(bimanual=True, use_velocity_and_torque=True)
    command = dict.fromkeys(a.action_names(), 10.0)
    assert a.step(command)["observation.state"] == b.step(command)["observation.state"]


# --- Synthetic 48-dim dataset -------------------------------------------------


def test_dataset_is_48_dim_and_carries_only_contract_keys() -> None:
    """info.json holds exactly the CTR-REC@v1 closed feature set — no out-of-contract key."""
    dataset = build_synthetic_dataset(frame_count=5)
    assert dataset.observation_dim() == 48
    config = RecorderConfig(
        bimanual=True, use_velocity_and_torque=True, camera_slots=dataset.config.camera_slots
    )
    assert set(dataset.info_features) == set(allowed_info_keys(config))


def test_dataset_camera_slot_round_trips_across_all_four_contracts() -> None:
    """One slot key joins the REC image key, the CAP sidecar column, and the WS tag."""
    dataset = build_synthetic_dataset(frame_count=3)
    for slot in dataset.config.camera_slots:
        assert slot_from_image_key(slot.image_key()) == slot
        assert slot_from_capture_ts_column(slot.capture_ts_column()) == slot
        assert slot_from_ws_tag(slot.ws_tag(FrameType.RGB)) == slot


def test_dataset_sidecar_joins_every_frame_on_frame_index() -> None:
    """Every dataset frame has a capture sidecar row at its frame_index."""
    dataset = build_synthetic_dataset(frame_count=6)
    sidecar_indices = {row.frame_index for row in dataset.sidecar.rows}
    assert sidecar_indices == {frame.frame_index for frame in dataset.frames}
    # Each sidecar capture column recovers a real recorded camera slot.
    for row in dataset.sidecar.rows:
        for slot in row.slots:
            assert slot.image_key() in dataset.frames[row.frame_index].images
