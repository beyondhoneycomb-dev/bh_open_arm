"""The WebXR pose source over the synthetic VR stream: samples, validity, frame flag.

The WebXR source is driven off the same deterministic stream the UDP path uses
(`contracts.fixtures.vr_pose_stream`), never a real headset — the real session is
deferred (test_deferred_reverify). This exercises the assembly of per-arm samples, the
non-blocking latest-snapshot read, the frame-already-applied declaration, and the
mapping of a lost pose to INVALID.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.teleop.webxr.session import Handedness, SessionError, TeleopMode
from backend.teleop.webxr.source import WebXrPoseSource
from contracts.fixtures.vr_pose_stream import SyntheticVrPoseStream
from contracts.teleop import TeleopValidity
from tests.wp3b08.support import (
    gamepad_from_sample,
    grip_from_sample,
    input_source,
    session,
    xr_standard_gamepad,
)


def test_frame_applied_is_declared_true() -> None:
    # The WebXR receiver applies the single world-frame transform upstream, so the
    # source declares it already applied (`FR-TEL-008`): no double transform here.
    assert WebXrPoseSource.frame_applied is True


def test_source_reads_a_sample_over_the_synthetic_stream(tmp_path: Path) -> None:
    sess = session(TeleopMode.RIGHT, tmp_path)
    sess.begin([input_source(Handedness.RIGHT)])
    source = WebXrPoseSource(sess)

    stream = SyntheticVrPoseStream()
    sample = stream.sample(3)
    grip = grip_from_sample(sample, "right")
    gamepad = gamepad_from_sample(sample, "right")

    out = source.read(
        Handedness.RIGHT,
        grip,
        gamepad,
        source_ts=sample.teleop_sample.source_ts,
        receive_mono_ns=sample.teleop_sample.receive_mono_ns,
    )
    assert out.validity is TeleopValidity.OK
    assert out.grip_pose == grip
    assert out.squeeze == pytest.approx(sample.grips["right"])
    # Both timestamps are preserved (`FR-TEL-022`).
    assert out.teleop_sample.source_ts == sample.teleop_sample.source_ts
    assert out.teleop_sample.receive_mono_ns == sample.teleop_sample.receive_mono_ns


def test_lost_pose_maps_to_invalid(tmp_path: Path) -> None:
    # WebXR has no native validity signal; a lost grip pose (getPose null) is INVALID.
    sess = session(TeleopMode.RIGHT, tmp_path)
    sess.begin([input_source(Handedness.RIGHT)])
    source = WebXrPoseSource(sess)
    out = source.read(Handedness.RIGHT, None, xr_standard_gamepad(), 1.0, 1)
    assert out.validity is TeleopValidity.INVALID
    assert out.grip_pose is None


def test_latest_is_a_nonblocking_snapshot(tmp_path: Path) -> None:
    sess = session(TeleopMode.RIGHT, tmp_path)
    sess.begin([input_source(Handedness.RIGHT)])
    source = WebXrPoseSource(sess)
    assert source.latest(Handedness.RIGHT) is None
    first = source.read(Handedness.RIGHT, None, xr_standard_gamepad(squeeze=0.2), 1.0, 1)
    assert source.latest(Handedness.RIGHT) is first
    second = source.read(Handedness.RIGHT, None, xr_standard_gamepad(squeeze=0.8), 2.0, 2)
    assert source.latest(Handedness.RIGHT) is second


def test_single_arm_source_reads_only_the_active_arm(tmp_path: Path) -> None:
    # ④: a right-only session cannot read the inactive left arm.
    sess = session(TeleopMode.RIGHT, tmp_path)
    sess.begin([input_source(Handedness.RIGHT)])
    source = WebXrPoseSource(sess)
    assert source.mode is TeleopMode.RIGHT
    with pytest.raises(SessionError):
        source.read(Handedness.LEFT, None, xr_standard_gamepad(), 1.0, 1)


def test_squeeze_tracks_the_stream_grip(tmp_path: Path) -> None:
    sess = session(TeleopMode.BIMANUAL, tmp_path)
    sess.begin([input_source(Handedness.LEFT), input_source(Handedness.RIGHT)])
    source = WebXrPoseSource(sess)
    stream = SyntheticVrPoseStream()
    for index in range(5):
        sample = stream.sample(index)
        for side, hand in (("left", Handedness.LEFT), ("right", Handedness.RIGHT)):
            out = source.read(
                hand,
                grip_from_sample(sample, side),
                gamepad_from_sample(sample, side),
                source_ts=sample.teleop_sample.source_ts,
                receive_mono_ns=sample.teleop_sample.receive_mono_ns,
            )
            assert out.squeeze == pytest.approx(sample.grips[side])
