"""Acceptance ③④: the guarded torque-ON ordering and the no-arbitrary-target guard.

The order is the safety property — present-pose read must precede 0xFC, and 0xFC must carry
the present pose, never an arbitrary target. The offline half of the bounce check (④) is
that the engage commands zero displacement; the physical joint movement is deferred.
"""

from __future__ import annotations

import dataclasses

import pytest

from backend.torque_bringup import (
    GuardedTorqueOn,
    SafeHoldViolationError,
    TorqueEngageSequenceError,
    TorqueOnManifest,
    TorqueOnRefusedError,
    build_present_pose_hold,
)
from backend.torque_bringup.sequence import _assert_targets_are_present_pose
from contracts.action import ExecutedMitCommand
from contracts.units import Nm, Rad, RadPerSec
from tests.wp105.conftest import RecordingEngageBus


def test_engage_reads_present_pose_before_0xfc(
    recording_bus: RecordingEngageBus, passing_manifest: TorqueOnManifest
) -> None:
    # Acceptance ③: present-pose read -> hold target -> 0xFC, in that order.
    session = GuardedTorqueOn(recording_bus, passing_manifest)
    session.engage()
    assert recording_bus.calls == ["read_present_pose", "engage_hold"]


def test_engage_holds_the_present_pose(
    recording_bus: RecordingEngageBus,
    passing_manifest: TorqueOnManifest,
    present_pose: tuple[Rad, ...],
) -> None:
    # Acceptance ③: the engaged frame's targets are exactly the present pose.
    session = GuardedTorqueOn(recording_bus, passing_manifest)
    result = session.engage()
    assert tuple(command.q for command in result.hold_batch) == present_pose
    assert recording_bus.engaged_batch == result.hold_batch


def test_engage_commands_zero_displacement(
    recording_bus: RecordingEngageBus, passing_manifest: TorqueOnManifest
) -> None:
    # Acceptance ④ (offline half): no bounce — the engage commands zero displacement.
    session = GuardedTorqueOn(recording_bus, passing_manifest)
    result = session.engage()
    assert set(result.commanded_displacement_rad()) == {0.0}


def test_engaged_hold_is_not_torque_zero(
    recording_bus: RecordingEngageBus, passing_manifest: TorqueOnManifest
) -> None:
    # The engaged hold is a gravity-comp hold: every joint carries kp > 0 (acceptance ⑫).
    session = GuardedTorqueOn(recording_bus, passing_manifest)
    result = session.engage()
    assert all(command.kp > 0.0 for command in result.hold_batch)


def test_preconditions_run_before_any_bus_read(
    recording_bus: RecordingEngageBus, passing_manifest: TorqueOnManifest
) -> None:
    # A failing precondition refuses before the bus is ever touched: no read, no 0xFC.
    manifest = dataclasses.replace(
        passing_manifest,
        gateway_bypass=dataclasses.replace(passing_manifest.gateway_bypass, bypass_count=1),
    )
    session = GuardedTorqueOn(recording_bus, manifest)
    with pytest.raises(TorqueOnRefusedError):
        session.engage()
    assert recording_bus.calls == []
    assert not session.engaged


def test_second_engage_refused(
    recording_bus: RecordingEngageBus, passing_manifest: TorqueOnManifest
) -> None:
    # Re-engaging would re-power a possibly-moved pose; the session engages at most once.
    session = GuardedTorqueOn(recording_bus, passing_manifest)
    session.engage()
    with pytest.raises(TorqueEngageSequenceError, match="already engaged"):
        session.engage()


def test_arbitrary_target_engage_is_rejected(present_pose: tuple[Rad, ...]) -> None:
    # Acceptance ③: a hold frame whose targets are not the present pose is refused —
    # there is no path to engage 0xFC on an arbitrary target.
    shifted = tuple(
        ExecutedMitCommand(
            kp=40.0, kd=1.0, q=Rad(angle.value + 0.5), dq=RadPerSec(0.0), tau=Nm(0.0)
        )
        for angle in present_pose
    )
    with pytest.raises(TorqueEngageSequenceError, match="not the present pose"):
        _assert_targets_are_present_pose(shifted, present_pose)


def test_present_pose_hold_rejects_zero_stiffness(present_pose: tuple[Rad, ...]) -> None:
    # build_present_pose_hold refuses to produce a torque-0 frame (kp<=0) as a SAFE_HOLD.
    # positions_to_batch always sets kp>0, so this guards the invariant at the source.
    hold = build_present_pose_hold(present_pose)
    assert all(command.kp > 0.0 for command in hold)
    limp = tuple(dataclasses.replace(command, kp=0.0) for command in hold)
    from backend.torque_bringup import assert_safe_hold

    with pytest.raises(SafeHoldViolationError):
        assert_safe_hold(limp)
