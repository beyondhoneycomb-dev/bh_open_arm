"""The resume point is a trajectory index, and repeated human aborts escalate (`02b` §2.3).

An abort records the trajectory index it stopped at (③); a resume refuses to continue over
an un-acknowledged safety latch, and once the operator has cleared it, continues from that
exact index so the commanded stream is the whole trajectory with no gap or repeat. A human
who aborts the same session three times surfaces `FAIL_BLOCKING` — the rig is indicted, not
the trajectory.
"""

from __future__ import annotations

import pytest

from backend.dynamics import ARM_JOINT_COUNT
from backend.excitation import (
    AbortCause,
    InjectionStatus,
    LatchStillEngagedError,
    Observer,
    SafeInitialState,
    TickObservation,
    TrajectorySample,
)
from backend.excitation.constants import REPEATED_HUMAN_ABORT_LIMIT
from tests.wp2b06.support import HEALTHY_BYTE, REST_POSE, build_context, healthy_tick

_ABORT_INDEX = 6


def _confirmed() -> SafeInitialState:
    return SafeInitialState(True, True, True, REST_POSE)


def _abort_once_observer(abort_index: int) -> Observer:
    """Abort (human) the first time `abort_index` is reached, then report clean."""
    fired = {"done": False}

    def _observe(index: int, sample: TrajectorySample) -> TickObservation:
        if index == abort_index and not fired["done"]:
            fired["done"] = True
            tick = healthy_tick(sample.positions_rad, sample.velocities_rad_s)
            return TickObservation(
                status_bytes=tick.status_bytes,
                motor_temps_c=tick.motor_temps_c,
                positions_rad=tick.positions_rad,
                velocities_rad_s=tick.velocities_rad_s,
                human_abort=True,
            )
        return healthy_tick(sample.positions_rad, sample.velocities_rad_s)

    return _observe


def _always_human_abort_observer() -> Observer:
    def _observe(index: int, sample: TrajectorySample) -> TickObservation:
        return TickObservation(
            status_bytes=[HEALTHY_BYTE] * ARM_JOINT_COUNT,
            motor_temps_c=[25.0] * ARM_JOINT_COUNT,
            positions_rad=list(sample.positions_rad),
            velocities_rad_s=list(sample.velocities_rad_s),
            human_abort=True,
        )

    return _observe


def test_abort_records_resume_index() -> None:
    context = build_context(_abort_once_observer(_ABORT_INDEX))
    result = context.injector.start(_confirmed())
    assert result.resume_index == _ABORT_INDEX
    assert context.injector.resume_index == _ABORT_INDEX


def test_resume_over_engaged_latch_refused() -> None:
    # 12 FR-SAF-043: resuming while the abort latch is still held would be an auto-resume.
    context = build_context(_abort_once_observer(_ABORT_INDEX))
    context.injector.start(_confirmed())
    assert context.latch.is_active is True
    with pytest.raises(LatchStillEngagedError):
        context.injector.resume(_confirmed())


def test_resume_from_index_completes_without_gap_or_repeat() -> None:
    context = build_context(_abort_once_observer(_ABORT_INDEX))
    context.injector.start(_confirmed())
    context.latch.acknowledge()  # the operator clears the hold
    result = context.injector.resume(_confirmed())
    assert result.status is InjectionStatus.COMPLETED
    assert context.torque_path is not None
    # The whole trajectory was commanded exactly once across the two drives.
    assert context.torque_path.commanded_indices == list(range(context.trajectory.sample_count))


def test_resumed_command_matches_the_trajectory_sample() -> None:
    context = build_context(_abort_once_observer(_ABORT_INDEX))
    context.injector.start(_confirmed())
    context.latch.acknowledge()
    context.injector.resume(_confirmed())
    assert context.torque_path is not None
    resumed = next(c for c in context.torque_path.commands if c.index == _ABORT_INDEX)
    expected = context.trajectory.sample(_ABORT_INDEX)
    assert resumed.positions_rad == expected.positions_rad


def test_repeated_human_abort_escalates_to_fail_blocking() -> None:
    context = build_context(_always_human_abort_observer())
    first = context.injector.start(_confirmed())
    assert first.cause is AbortCause.HUMAN_ABORT
    assert first.fail_blocking is False
    for _ in range(REPEATED_HUMAN_ABORT_LIMIT - 2):
        context.latch.acknowledge()
        interim = context.injector.resume(_confirmed())
        assert interim.fail_blocking is False
    context.latch.acknowledge()
    final = context.injector.resume(_confirmed())
    assert context.injector.human_abort_count == REPEATED_HUMAN_ABORT_LIMIT
    assert final.fail_blocking is True
