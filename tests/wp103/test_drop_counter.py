"""Acceptance ⑮ — the CAN packet-drop count is surfaced as an observation feature.

LeRobot logs a packet drop and reuses the last state; the count never becomes a
feature (`01` FR-SYS-018). The `DropCounter` attaches to the Damiao logger and counts
those records, and the follower surfaces the tally under `can_packet_drop_count`, so a
consumer sees drops rather than losing them to a warning that vanishes.
"""

from __future__ import annotations

import logging
from pathlib import Path

from backend.actuation import DropCounter
from backend.actuation.bus_writer import DAMIAO_LOGGER_NAME, DROP_LOG_PREFIX
from contracts.action import DROP_COUNTER_META
from contracts.plugin.config import Side
from packages.lerobot_robot_openarm.config_oa import (
    BiOaOpenArmFollowerConfig,
    OaOpenArmFollowerConfig,
)
from packages.lerobot_robot_openarm.openarm_follower_oa import (
    BiOaOpenArmFollower,
    OaOpenArmFollower,
)
from tests.wp103.conftest import FakeArmBus


def _emit_drop(count: int = 1) -> None:
    """Emit `count` packet-drop warnings on the Damiao logger, as the bus would."""
    logger = logging.getLogger(DAMIAO_LOGGER_NAME)
    for index in range(count):
        logger.warning(f"{DROP_LOG_PREFIX}: joint_{index} (ID: 0x11). Using last known state.")


def test_drop_counter_counts_packet_drop_records() -> None:
    """A packet-drop log record increments the counter; an unrelated one does not (⑮)."""
    counter = DropCounter()
    counter.attach()
    try:
        _emit_drop(3)
        logging.getLogger(DAMIAO_LOGGER_NAME).warning("some other warning")
        assert counter.count == 3
    finally:
        counter.detach()


def test_detached_counter_stops_counting() -> None:
    """A detached counter no longer counts — attachment is what surfaces the tally (⑮)."""
    counter = DropCounter()
    counter.attach()
    _emit_drop(1)
    counter.detach()
    _emit_drop(5)
    assert counter.count == 1


def test_follower_surfaces_drop_count_as_observation_feature(tmp_path: Path) -> None:
    """The follower's observation carries `can_packet_drop_count` from the counter (⑮)."""
    counter = DropCounter()
    config = OaOpenArmFollowerConfig(side=Side.LEFT, id="drop_arm", calibration_dir=tmp_path)
    follower = OaOpenArmFollower(config, bus=FakeArmBus(), drop_counter=counter)
    follower.enable_drop_counting()
    try:
        _emit_drop(2)
        observation = follower.get_observation()
        assert observation[DROP_COUNTER_META] == 2
    finally:
        follower.disable_drop_counting()


def _bimanual(tmp_path: Path) -> BiOaOpenArmFollower:
    """Build a bimanual follower over two fixture buses, opening nothing.

    `use_velocity_and_torque` is on because `observation_features` is frozen at the full
    48 channels and the F24 session-start check (`ops.telemetry.velocity_torque`) refuses
    to start a recording with it off — so this is the only configuration in which a
    dataset is ever built from that declaration.
    """
    config = BiOaOpenArmFollowerConfig(
        id="bi_drop", calibration_dir=tmp_path, use_velocity_and_torque=True
    )
    left = OaOpenArmFollower(
        OaOpenArmFollowerConfig(
            side=Side.LEFT,
            id="bi_drop_left",
            calibration_dir=tmp_path,
            use_velocity_and_torque=True,
        ),
        bus=FakeArmBus(),
    )
    right = OaOpenArmFollower(
        OaOpenArmFollowerConfig(
            side=Side.RIGHT,
            id="bi_drop_right",
            calibration_dir=tmp_path,
            use_velocity_and_torque=True,
        ),
        bus=FakeArmBus(),
    )
    return BiOaOpenArmFollower(config, left=left, right=right)


def test_bimanual_observation_keys_are_exactly_its_declared_features(tmp_path: Path) -> None:
    """The frame the robot emits and the features it declares must be one set.

    LeRobot builds a dataset's feature set from `observation_features`, so a key the frame
    produces but the declaration omits is discarded and a key the declaration promises but
    the frame omits is missing from every episode. The two are written in different files
    and nothing else compares them — both sides keep passing their own checks after one
    drifts, and the mismatch surfaces only as an absent column in recorded data.
    """
    bimanual = _bimanual(tmp_path)

    assert set(bimanual.get_observation()) == set(bimanual.observation_features)


def test_bimanual_drop_count_is_one_unprefixed_robot_total(tmp_path: Path) -> None:
    """The counter is observation meta for the robot, not a per-arm channel (⑮).

    Prefixed, the FR-SYS-018 tally leaves the declared feature set entirely, and a
    bimanual episode recorded over a lossy bus becomes indistinguishable from a clean one.
    """
    bimanual = _bimanual(tmp_path)
    observation = bimanual.get_observation()

    assert DROP_COUNTER_META in observation
    assert f"left_{DROP_COUNTER_META}" not in observation
    assert f"right_{DROP_COUNTER_META}" not in observation
