"""Plugin config is validated at assembly time, not at record-loop runtime (WP-0A-02).

Acceptance ⑤: a follower config with `side` unset is refused at construction —
the LeRobot default (+/-5 degree limits) is unusable (01 FR-SYS-013). Acceptance
⑥: a follower and leader whose `use_velocity_and_torque` disagree are refused
before a session starts, ahead of the runtime KeyError LeRobot would otherwise
raise in `build_dataset_frame` (01 FR-SYS-012).
"""

from __future__ import annotations

import pytest

from contracts.plugin import (
    BimanualSessionConfig,
    ConfigError,
    FollowerConfig,
    LeaderConfig,
    Side,
    validate_teleop_pairing,
)


def test_side_present_is_accepted() -> None:
    """A follower that names its side constructs."""
    assert FollowerConfig(side=Side.LEFT, use_velocity_and_torque=True).side is Side.LEFT


def test_side_unset_is_rejected() -> None:
    """A follower with side left None is refused at construction (acceptance ⑤)."""
    with pytest.raises(ConfigError, match="side"):
        FollowerConfig(side=None, use_velocity_and_torque=True)  # type: ignore[arg-type]


def test_matched_velocity_torque_switch_is_accepted() -> None:
    """A follower and leader that agree on the switch pair cleanly."""
    validate_teleop_pairing(
        FollowerConfig(side=Side.LEFT, use_velocity_and_torque=True),
        LeaderConfig(use_velocity_and_torque=True),
    )


def test_velocity_torque_mismatch_is_rejected() -> None:
    """A follower/leader switch mismatch is refused (acceptance ⑥)."""
    with pytest.raises(ConfigError, match="use_velocity_and_torque"):
        validate_teleop_pairing(
            FollowerConfig(side=Side.LEFT, use_velocity_and_torque=True),
            LeaderConfig(use_velocity_and_torque=False),
        )


def test_bimanual_applies_switch_to_both_arms() -> None:
    """A bimanual session validates the switch across both arms and the leader."""
    session = BimanualSessionConfig(
        left=FollowerConfig(side=Side.LEFT, use_velocity_and_torque=True),
        right=FollowerConfig(side=Side.RIGHT, use_velocity_and_torque=True),
        leader=LeaderConfig(use_velocity_and_torque=True),
    )
    assert session.left.side is Side.LEFT


def test_bimanual_one_arm_mismatch_is_rejected() -> None:
    """A bimanual session with one arm's switch off is refused (01 FR-SYS-012)."""
    with pytest.raises(ConfigError, match="use_velocity_and_torque"):
        BimanualSessionConfig(
            left=FollowerConfig(side=Side.LEFT, use_velocity_and_torque=True),
            right=FollowerConfig(side=Side.RIGHT, use_velocity_and_torque=False),
            leader=LeaderConfig(use_velocity_and_torque=True),
        )


def test_bimanual_swapped_sides_is_rejected() -> None:
    """A bimanual session with left/right sides swapped is refused."""
    with pytest.raises(ConfigError, match="side"):
        BimanualSessionConfig(
            left=FollowerConfig(side=Side.RIGHT, use_velocity_and_torque=True),
            right=FollowerConfig(side=Side.LEFT, use_velocity_and_torque=True),
            leader=LeaderConfig(use_velocity_and_torque=True),
        )
