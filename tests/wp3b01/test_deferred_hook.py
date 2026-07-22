"""DEFERRED — real enumeration skips with a reason, and its re-verification hook runs.

Real enumeration (real serials, real link speeds, a real first-frame grab) needs
cameras this host lacks, so `real_connect_supported()` reports why it cannot run and a
real test would SKIP on that reason (`02a` §4.1). The hook that the deferral must ship
is `reconnect_from_fixture`: given a directory of real captured output it re-runs the
identical tolerant connect over the real bytes, so no path is re-implemented for
hardware. Here the "real" directory is written to `tmp_path` to exercise the hook.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.sensing.connect import (
    REAL_FIXTURE_ENV_VAR,
    ConnectStatus,
    SkipReason,
    fixture_dir_from_env,
    real_connect_supported,
    reconnect_from_fixture,
)


def test_real_connect_reports_support_and_a_reason() -> None:
    """Support is a (bool, reason) pair; when unsupported the reason is non-empty."""
    supported, reason = real_connect_supported()
    assert isinstance(supported, bool)
    if not supported:
        assert reason  # a skip must carry why, never a fabricated green
    else:  # pragma: no cover — this host has no camera backends
        assert reason == ""


def test_real_connect_skips_without_backends() -> None:
    """The bound real test skips with the reason rather than asserting a fake pass."""
    supported, reason = real_connect_supported()
    if not supported:
        pytest.skip(f"real camera enumeration unavailable: {reason}")


def _write_fixture(root: Path, *, liveness: dict[str, bool]) -> Path:
    """Write a real-shaped capture directory (descriptors + binding + liveness)."""
    descriptors = [
        {
            "serial": "rs-0001",
            "camera_type": "intelrealsense",
            "model": "Intel RealSense D435",
            "profiles": [{"width": 640, "height": 480, "fps": 30, "bpp": 2, "stream_kind": "rgb"}],
            "controller": "usb-controller-0",
            "link_speed": "usb3",
        },
        {
            "serial": "uvc-heavy-720",
            "camera_type": "opencv",
            "model": "Generic UVC",
            "profiles": [{"width": 1280, "height": 720, "fps": 30, "bpp": 3, "stream_kind": "rgb"}],
            "controller": "usb-controller-2",
            "link_speed": "usb2",
        },
    ]
    (root / "descriptors.json").write_text(json.dumps(descriptors), encoding="utf-8")
    (root / "binding.json").write_text(
        json.dumps({"wrist": "rs-0001", "fallback": "uvc-heavy-720"}), encoding="utf-8"
    )
    (root / "liveness.json").write_text(json.dumps(liveness), encoding="utf-8")
    return root


def test_reconnect_from_fixture_reruns_the_same_logic(tmp_path: Path) -> None:
    """A recorded-dead slot skips, a recorded-live USB2 slot opens and is flagged+blocked."""
    _write_fixture(tmp_path, liveness={"wrist": False, "fallback": True})
    report = reconnect_from_fixture(tmp_path)

    wrist = report.by_slot("wrist")
    assert wrist.status is ConnectStatus.SKIPPED
    assert wrist.reason is SkipReason.NO_FRAME

    fallback = report.by_slot("fallback")
    assert fallback.status is ConnectStatus.OPENED
    assert fallback.is_usb2_fallback
    assert len(fallback.blocked_profiles) == 1  # 663 Mbps > 480 Mbps USB2 budget

    assert report.arm_may_proceed is True


def test_reconnect_missing_liveness_treats_enumerated_as_live(tmp_path: Path) -> None:
    """A slot with no recorded liveness is taken as live, since it enumerated."""
    _write_fixture(tmp_path, liveness={})
    report = reconnect_from_fixture(tmp_path)
    assert report.by_slot("wrist").is_opened
    assert report.by_slot("fallback").is_opened


def test_reconnect_requires_descriptors(tmp_path: Path) -> None:
    """A capture with no descriptors is an error, not a silent empty report."""
    (tmp_path / "binding.json").write_text(json.dumps({"wrist": "rs-0001"}), encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="descriptors.json"):
        reconnect_from_fixture(tmp_path)


def test_fixture_dir_from_env_unset_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """With the env var unset, the hook has no fixture and a bound test skips."""
    monkeypatch.delenv(REAL_FIXTURE_ENV_VAR, raising=False)
    assert fixture_dir_from_env() is None


def test_fixture_dir_from_env_points_at_a_real_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the env var names an existing directory, the hook resolves to it."""
    _write_fixture(tmp_path, liveness={"wrist": True, "fallback": True})
    monkeypatch.setenv(REAL_FIXTURE_ENV_VAR, str(tmp_path))
    resolved = fixture_dir_from_env()
    assert resolved == tmp_path
    report = reconnect_from_fixture(resolved)
    assert report.arm_may_proceed is True
