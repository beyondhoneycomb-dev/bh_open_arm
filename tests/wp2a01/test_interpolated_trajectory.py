"""Acceptance ② — one step is emitted as an interpolated trajectory, not one command.

FR-MAN-010 forbids sending a jog step as a single `send_action`: a step must be an
interpolated trajectory. Through the real scheduler, that means one step produces
`round(hz * duration)` accepted emissions whose commanded angle sweeps from the
origin to the target — never a single repeated command. The count and the sweep are
what these tests assert, driven waypoint-by-waypoint through the Wave-1 scheduler.
"""

from __future__ import annotations

import math
from itertools import pairwise

import pytest

from backend.actuation import EmissionLabel
from backend.jog import (
    Arm,
    JogAddress,
    JogDirection,
    frame_count,
    plan_step_trajectory,
)
from contracts.units import Deg
from tests.wp2a01.bench import NEUTRAL_REQUEST, JogSchedulerBench

_REFERENCE_HZ = 50.0
_REFERENCE_DURATION_SEC = 2.0
_STEP_DEG = 5.0


def _accepted_joint_angles(bench: JogSchedulerBench, index: int) -> list[float]:
    """Play a step through the bench and return the addressed joint's commanded radians."""
    address = JogAddress(Arm.LEFT, 3)
    trajectory = plan_step_trajectory(
        origin=NEUTRAL_REQUEST,
        address=address,
        direction=JogDirection.PLUS,
        step=Deg(_STEP_DEG),
        start_mono=0.0,
        hz=_REFERENCE_HZ,
        duration=_REFERENCE_DURATION_SEC,
    )
    emissions = bench.follow_trajectory(trajectory)
    accepted = [e for e in emissions if e.label is EmissionLabel.ACCEPTED_TARGET]
    return [emission.batch[index].q.value for emission in accepted]


def test_one_step_emits_hz_times_duration_frames() -> None:
    """A single step is accepted as `hz × duration` emissions, one per waypoint."""
    bench = JogSchedulerBench()
    address = JogAddress(Arm.LEFT, 3)

    trajectory = plan_step_trajectory(
        origin=NEUTRAL_REQUEST,
        address=address,
        direction=JogDirection.PLUS,
        step=Deg(_STEP_DEG),
        start_mono=0.0,
        hz=_REFERENCE_HZ,
        duration=_REFERENCE_DURATION_SEC,
    )
    expected_frames = frame_count(_REFERENCE_HZ, _REFERENCE_DURATION_SEC)
    assert expected_frames == 100

    emissions = bench.follow_trajectory(trajectory)
    accepted = [e for e in emissions if e.label is EmissionLabel.ACCEPTED_TARGET]

    # Every waypoint became exactly one accepted CAN frame: emitted == hz × duration.
    assert len(emissions) == expected_frames
    assert len(accepted) == expected_frames


def test_step_is_a_sweep_not_a_single_command() -> None:
    """The commanded angle rises monotonically from origin to target across the step."""
    bench = JogSchedulerBench()
    index = JogAddress(Arm.LEFT, 3).index

    angles = _accepted_joint_angles(bench, index)

    # A single-command implementation would repeat one value; an interpolated one
    # sweeps. The addressed joint is strictly increasing across all frames.
    assert all(later > earlier for earlier, later in pairwise(angles))
    assert len(set(angles)) == len(angles)
    assert angles[0] == pytest.approx(0.0)
    assert angles[-1] == pytest.approx(math.radians(_STEP_DEG))


@pytest.mark.parametrize(
    ("hz", "duration"),
    [(50.0, 2.0), (10.0, 1.0), (100.0, 0.5), (25.0, 4.0)],
)
def test_emitted_frame_count_tracks_hz_and_duration(hz: float, duration: float) -> None:
    """For several cadences the accepted-frame count equals `round(hz × duration)`."""
    bench = JogSchedulerBench()
    trajectory = plan_step_trajectory(
        origin=NEUTRAL_REQUEST,
        address=JogAddress(Arm.RIGHT, 1),
        direction=JogDirection.MINUS,
        step=Deg(1.0),
        start_mono=0.0,
        hz=hz,
        duration=duration,
    )
    emissions = bench.follow_trajectory(trajectory)
    accepted = [e for e in emissions if e.label is EmissionLabel.ACCEPTED_TARGET]

    assert len(accepted) == frame_count(hz, duration)
