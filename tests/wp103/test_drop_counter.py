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
from packages.lerobot_robot_openarm.config_oa import OaOpenArmFollowerConfig
from packages.lerobot_robot_openarm.openarm_follower_oa import OaOpenArmFollower
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
