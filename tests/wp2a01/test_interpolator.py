"""Unit tests for the `np.linspace` jog interpolator (planning, pure)."""

from __future__ import annotations

from itertools import pairwise

import pytest

from backend.jog import (
    Arm,
    JogAddress,
    JogDirection,
    frame_count,
    plan_continuous_trajectory,
    plan_step_trajectory,
)
from contracts.action import BIMANUAL_ACTION_DIM, RequestedPositionAction
from contracts.units import Deg, DegPerSec

_HZ = 50.0
_DURATION = 2.0


def _origin() -> RequestedPositionAction:
    """A non-trivial origin so single-joint isolation is observable on every joint."""
    return RequestedPositionAction(values=tuple(Deg(float(index)) for index in range(16)))


def _joint_track(request_values: tuple[tuple[Deg, ...], ...], index: int) -> list[float]:
    """Return one joint's degree track across a sequence of waypoint value tuples."""
    return [values[index].value for values in request_values]


def test_frame_count_is_hz_times_duration() -> None:
    """The emitted frame count is `round(hz × duration)`, at least one."""
    assert frame_count(50.0, 2.0) == 100
    assert frame_count(10.0, 1.0) == 10
    assert frame_count(100.0, 0.5) == 50
    assert frame_count(1.0, 0.4) == 1  # rounds to at least one frame


@pytest.mark.parametrize(("hz", "duration"), [(0.0, 1.0), (-1.0, 1.0), (50.0, 0.0), (50.0, -2.0)])
def test_frame_count_rejects_non_positive(hz: float, duration: float) -> None:
    """A non-positive cadence or duration is a ValueError."""
    with pytest.raises(ValueError, match="must be positive"):
        frame_count(hz, duration)


def test_step_endpoints_are_origin_and_target() -> None:
    """The first waypoint re-commands the origin; the last commands the stepped target."""
    address = JogAddress(Arm.LEFT, 3)
    trajectory = plan_step_trajectory(
        _origin(), address, JogDirection.PLUS, Deg(5.0), start_mono=0.0, hz=_HZ, duration=_DURATION
    )

    first = trajectory.waypoints[0].request.values
    last = trajectory.waypoints[-1].request.values
    assert first[address.index] == Deg(2.0)  # origin value at index 2
    assert last[address.index] == Deg(7.0)  # 2.0 + 5.0


def test_step_moves_only_the_addressed_joint() -> None:
    """Every joint but the addressed one holds its origin value across all waypoints."""
    address = JogAddress(Arm.RIGHT, 4)  # index 11
    trajectory = plan_step_trajectory(
        _origin(), address, JogDirection.PLUS, Deg(5.0), start_mono=0.0, hz=_HZ, duration=_DURATION
    )
    tracks = tuple(waypoint.request.values for waypoint in trajectory.waypoints)

    for index in range(BIMANUAL_ACTION_DIM):
        track = _joint_track(tracks, index)
        if index == address.index:
            assert track[0] < track[-1]  # the addressed joint moved
        else:
            assert len(set(track)) == 1  # every other joint stayed put


def test_step_direction_sign() -> None:
    """`−` decreases the addressed joint; `+` increases it."""
    address = JogAddress(Arm.LEFT, 2)
    down = plan_step_trajectory(_origin(), address, JogDirection.MINUS, Deg(1.0), start_mono=0.0)
    values = down.waypoints
    assert values[-1].request.values[address.index] == Deg(0.0)  # origin 1.0 − 1.0


def test_step_waypoint_times_are_evenly_spaced() -> None:
    """Waypoint times start at `start_mono` and step by `1/hz`."""
    trajectory = plan_step_trajectory(
        _origin(),
        JogAddress(Arm.LEFT, 1),
        JogDirection.PLUS,
        Deg(0.5),
        start_mono=10.0,
        hz=_HZ,
        duration=_DURATION,
    )
    interval = 1.0 / _HZ
    assert trajectory.waypoints[0].at == pytest.approx(10.0)
    assert trajectory.waypoints[1].at == pytest.approx(10.0 + interval)
    assert trajectory.waypoints[-1].at == pytest.approx(10.0 + (len(trajectory) - 1) * interval)


def test_step_rejects_off_vocabulary_size() -> None:
    """A step outside the offered vocabulary is refused before any trajectory is built."""
    with pytest.raises(ValueError, match="not one of"):
        plan_step_trajectory(
            _origin(), JogAddress(Arm.LEFT, 1), JogDirection.PLUS, Deg(2.0), start_mono=0.0
        )


def test_continuous_moves_addressed_joint_by_velocity_over_duration() -> None:
    """Continuous mode sweeps the joint by `velocity × duration`, others held."""
    address = JogAddress(Arm.LEFT, 5)  # index 4, origin 4.0
    trajectory = plan_continuous_trajectory(
        _origin(),
        address,
        JogDirection.PLUS,
        DegPerSec(3.0),
        start_mono=0.0,
        hz=_HZ,
        duration=_DURATION,
    )

    assert len(trajectory) == frame_count(_HZ, _DURATION)
    track = _joint_track(tuple(w.request.values for w in trajectory.waypoints), address.index)
    assert track[0] == pytest.approx(4.0)
    assert track[-1] == pytest.approx(4.0 + 3.0 * _DURATION)  # 4.0 + 6.0
    assert all(later > earlier for earlier, later in pairwise(track))


def test_continuous_holds_every_other_joint() -> None:
    """A continuous jog leaves the other fifteen joints exactly at their origin."""
    address = JogAddress(Arm.RIGHT, 2)
    trajectory = plan_continuous_trajectory(
        _origin(), address, JogDirection.MINUS, DegPerSec(2.0), start_mono=0.0
    )
    tracks = tuple(waypoint.request.values for waypoint in trajectory.waypoints)

    for index in range(BIMANUAL_ACTION_DIM):
        if index == address.index:
            continue
        assert len(set(_joint_track(tracks, index))) == 1
