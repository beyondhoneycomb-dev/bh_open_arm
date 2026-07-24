"""Acceptance ③/`FR-DAT-016`: every channel axis label carries its unit.

A single `observation.state` vector mixes deg (`.pos`), deg/s (`.vel`) and Nm
(`.torque`); an unlabelled plot misreads a torque as degrees. The viewer must
label 100% of channels with the right unit.
"""

from __future__ import annotations

from backend.dataset.viewer import axis_label, unit_for_channel
from backend.dataset.viewer.constants import UNKNOWN_UNIT
from backend.dataset.viewer.episode_viewer import EpisodeViewer


def test_suffix_units() -> None:
    assert unit_for_channel("left_joint_1.pos") == "deg"
    assert unit_for_channel("left_joint_1.vel") == "deg/s"
    assert unit_for_channel("right_gripper.torque") == "Nm"


def test_axis_label_includes_unit() -> None:
    assert axis_label("left_joint_1.pos") == "left_joint_1.pos [deg]"
    assert axis_label("right_gripper.torque") == "right_gripper.torque [Nm]"


def test_every_state_channel_is_unit_labelled(episode0: EpisodeViewer) -> None:
    # 100% coverage: no state channel resolves to the unknown-unit placeholder.
    for name in episode0.signals.state_names:
        unit = unit_for_channel(name)
        assert unit != UNKNOWN_UNIT, name
        assert unit in {"deg", "deg/s", "Nm"}, name


def test_state_vector_mixes_three_units(episode0: EpisodeViewer) -> None:
    units = {unit_for_channel(name) for name in episode0.signals.state_names}
    # The vel/torque dataset carries all three units in one vector.
    assert units == {"deg", "deg/s", "Nm"}
