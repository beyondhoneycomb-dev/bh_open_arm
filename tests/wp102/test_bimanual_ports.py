"""Each arm of the pair opens the channel the operator identified it on, not a side default.

`PORT_BY_SIDE` maps left to `can0` and right to `can1`, and the module that declares it says
plainly that this is a placeholder and never evidence: the two arms answer on the same CAN ids
(`03` §2.1), so nothing on the bus separates them and the adapter has been seen at more than one
USB port path. The operator's identification is the only evidence there is.

`OaOpenArmFollower` has taken a `port` for exactly this reason. The pair did not forward one, so
a bimanual caller holding the operator's answer had no way to apply it — every pair fell back to
the placeholder, and a placeholder that happens to be right is indistinguishable from an answer
until the arms swap and a left command reaches a right arm.

Nothing here opens a bus: the constructor builds both arms and connects neither.
"""

from __future__ import annotations

from pathlib import Path

from packages.lerobot_robot_openarm.config_oa import BiOaOpenArmFollowerConfig
from packages.lerobot_robot_openarm.openarm_follower_oa import (
    PORT_BY_SIDE,
    BiOaOpenArmFollower,
)

# Deliberately neither `can0` nor `can1`, and not in side order. Interfaces that matched the
# placeholder would pass against a pair that ignored the argument entirely, and interfaces in
# side order would pass against a pair that assigned them by position.
IDENTIFIED_PORTS = {"left": "can5", "right": "can2"}


def test_each_arm_opens_the_channel_it_was_identified_on(tmp_path: Path) -> None:
    """The operator's answer reaches both arms, and is not reordered on the way."""
    pair = BiOaOpenArmFollower(
        BiOaOpenArmFollowerConfig(id="ports", calibration_dir=tmp_path),
        ports=IDENTIFIED_PORTS,
    )

    assert pair.left_arm.config.port == IDENTIFIED_PORTS["left"]
    assert pair.right_arm.config.port == IDENTIFIED_PORTS["right"]


def test_no_answer_leaves_the_placeholder_standing(tmp_path: Path) -> None:
    """Absent an identification the pair keeps the side default, as one arm alone does.

    Kept rather than refused here because the offline flow never opens a socket, and every
    fixture and every test that builds a pair would otherwise have to carry a channel map. The
    refusal belongs where the bus is actually opened, and `backend.config.arm` makes it.
    """
    pair = BiOaOpenArmFollower(BiOaOpenArmFollowerConfig(id="default", calibration_dir=tmp_path))

    assert pair.left_arm.config.port == PORT_BY_SIDE["left"]
    assert pair.right_arm.config.port == PORT_BY_SIDE["right"]


def test_forwarding_a_port_does_not_split_the_pair_s_drop_counter(tmp_path: Path) -> None:
    """The counter stays one object, because the vendor logs both buses to one logger.

    Two counters would each hold the pair's total rather than their own arm's. The port travels
    through `_build_arm`, which is where that sharing lives, so this pins that the forwarding did
    not move arm construction out to the caller.
    """
    pair = BiOaOpenArmFollower(
        BiOaOpenArmFollowerConfig(id="counter", calibration_dir=tmp_path),
        ports=IDENTIFIED_PORTS,
    )

    assert pair.left_arm.drop_counter is pair.right_arm.drop_counter
