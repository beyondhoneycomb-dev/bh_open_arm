"""The bus speaks degrees and the judge measures radians, and nothing else notices the mistake.

`MOTION_THRESHOLD_RAD` is 0.05 rad and `DamiaoMotorsBus` decodes positions with
`np.degrees(...)`. Hand the judge degrees and it does not raise, it does not log, and it does not
produce a wrong arm — it produces an answer that can never resolve: every twitch clears a 0.05
"rad" motion gate while the quiet gate becomes 0.01°, which nothing on a live bus satisfies. So
the property is pinned from both sides: a real 2° reading must NOT clear the motion gate, and a
real 5° reading must resolve.
"""

from __future__ import annotations

import math

import pytest

from ops.hw.canbind import (
    MOTION_THRESHOLD_RAD,
    IdentificationResult,
    identify_moved_channel,
)
from scripts import canbind_session as session
from scripts.canbind_session_tests.canbind_doubles import (
    RESTING_ANGLE_DEG,
    FakeChannelBus,
    MoveArm,
    NobodyMoves,
)

# Below the 0.05 rad (2.9°) motion gate once converted, and far above it if the conversion is
# skipped. This is the number that separates a tool that works from one that always answers
# "more than one channel moved".
UNDER_GATE_DEG = 2.0

# The move the guide asks the operator for: one shoulder swing of five degrees or more.
OVER_GATE_DEG = 5.0

# A reading with an exact radian counterpart, for pinning the direction of the crossing.
KNOWN_ANGLE_DEG = 30.0

INTERFACES = ("can0", "can1")


@pytest.fixture
def motor_names() -> tuple[str, ...]:
    """The seven arm joints every channel is registered with."""
    return session.identification_motor_names()


def _round(motor_names: tuple[str, ...], move_deg: float) -> IdentificationResult:
    """Run one round in which the operator moves `can0`'s first joint by `move_deg` degrees."""
    buses = {name: FakeChannelBus(motor_names, RESTING_ANGLE_DEG) for name in INTERFACES}
    reader = session.ChannelJointReader(buses, motor_names)
    return identify_moved_channel(
        INTERFACES, reader, MoveArm(buses[INTERFACES[0]], motor_names[0], move_deg)
    )


def test_the_reader_hands_the_judge_radians(motor_names: tuple[str, ...]) -> None:
    """A 30° reading reaches the judge as 0.5236, not as 30 and not as 1718."""
    bus = FakeChannelBus(motor_names, KNOWN_ANGLE_DEG)
    reader = session.ChannelJointReader({INTERFACES[0]: bus}, motor_names)

    angles = reader(INTERFACES[0])

    assert list(angles) == [pytest.approx(math.radians(KNOWN_ANGLE_DEG))] * len(motor_names)


def test_two_degrees_does_not_clear_the_motion_gate(motor_names: tuple[str, ...]) -> None:
    """2° is 0.035 rad, under the gate. Unconverted it is 2.0 "rad" and clears it forty times over.

    This is the test that fails when the conversion is dropped, and it fails by resolving — the
    failure mode of the missing conversion is a confident answer, not an error.
    """
    result = _round(motor_names, UNDER_GATE_DEG)

    assert not result.resolved
    assert result.moved_interface is None
    assert str(MOTION_THRESHOLD_RAD) in result.reason


def test_five_degrees_resolves_the_channel_the_operator_moved(motor_names: tuple[str, ...]) -> None:
    """The move the guide asks for has to actually answer; a gate nothing clears is not a gate."""
    result = _round(motor_names, OVER_GATE_DEG)

    assert result.resolved
    assert result.moved_interface == INTERFACES[0]
    moved = {motion.interface: motion.max_delta_rad for motion in result.motions}
    assert moved[INTERFACES[0]] == pytest.approx(math.radians(OVER_GATE_DEG))
    assert moved[INTERFACES[1]] == pytest.approx(0.0)


def test_a_round_nobody_moved_stays_unresolved(motor_names: tuple[str, ...]) -> None:
    """No motion is a round to repeat, never a channel to pick."""
    buses = {name: FakeChannelBus(motor_names, RESTING_ANGLE_DEG) for name in INTERFACES}
    reader = session.ChannelJointReader(buses, motor_names)

    result = identify_moved_channel(INTERFACES, reader, NobodyMoves())

    assert not result.resolved
    assert result.moved_interface is None
