"""DEFERRED — a real headset skips with a reason, and its re-verification hook runs.

The ONE RULE: real VR (a Meta Quest APK stream) needs hardware this host lacks, so a
bound real test SKIPs on a stated reason rather than asserting a fabricated green
(`02a` §4.1, `PG-VR-001`). The hook the deferral must ship is `replay_from_capture`:
given a file of datagrams captured off a real headset it re-runs the *identical*
production parser over the real bytes. Here the capture is written to `tmp_path` (the
synthetic stream standing in for real bytes) to exercise the hook end to end.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.teleop.vr_udp import (
    REAL_FIXTURE_ENV_VAR,
    capture_path_from_env,
    parse_datagram,
    real_vr_supported,
    replay_from_capture,
)
from backend.teleop.vr_udp.deferred import CAPTURE_FILENAME, FrameParseError
from contracts.fixtures.vr_pose_stream import SyntheticVrPoseStream
from tests.wp3b07._support import datagram_from_sample


def test_real_vr_reports_support_and_a_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    """Support is a (bool, reason) pair; unsupported carries a non-empty reason."""
    monkeypatch.delenv(REAL_FIXTURE_ENV_VAR, raising=False)
    supported, reason = real_vr_supported()
    assert supported is False
    assert reason  # a skip must state why, never fabricate a green


def test_real_vr_skips_without_a_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    """The bound real test skips with the reason rather than asserting a fake pass."""
    monkeypatch.delenv(REAL_FIXTURE_ENV_VAR, raising=False)
    supported, reason = real_vr_supported()
    if not supported:
        pytest.skip(f"real Quest VR unavailable: {reason}")


def _write_capture(root: Path, count: int) -> Path:
    """Write a real-shaped capture: newline-terminated JSON datagrams, one per line."""
    stream = SyntheticVrPoseStream()
    capture = root / CAPTURE_FILENAME
    capture.write_bytes(b"".join(datagram_from_sample(stream, i) for i in range(count)))
    return capture


def test_env_capture_is_discovered(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A capture named by the environment is found and flips support to True."""
    _write_capture(tmp_path, 3)
    monkeypatch.setenv(REAL_FIXTURE_ENV_VAR, str(tmp_path))
    found = capture_path_from_env()
    assert found is not None
    assert found.name == CAPTURE_FILENAME
    supported, reason = real_vr_supported()
    assert supported is True
    assert reason == ""


def test_replay_reruns_the_production_parser(tmp_path: Path) -> None:
    """The hook re-parses real bytes through the same path — no code re-implemented."""
    capture = _write_capture(tmp_path, 5)
    frames = replay_from_capture(capture)
    assert len(frames) == 5
    stream = SyntheticVrPoseStream()
    for index, frame in enumerate(frames):
        # Identical transform: the replay reproduces the live parse exactly.
        expected = parse_datagram(datagram_from_sample(stream, index), receive_mono_ns=1)
        assert frame.arm("left").world_pose == expected.arm("left").world_pose
        assert frame.frame_applied is True
        assert frame.receive_mono_ns > 0  # a genuine receive instant, stamped at replay


def test_replay_surfaces_a_corrupt_capture(tmp_path: Path) -> None:
    """A corrupt line in the real capture is surfaced, not silently skipped."""
    capture = tmp_path / CAPTURE_FILENAME
    capture.write_bytes(b'{"broken": true}\n')
    with pytest.raises(FrameParseError):
        replay_from_capture(capture)
