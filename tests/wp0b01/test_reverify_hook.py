"""Acceptance ⑥ — the real-fixture re-verification hook (plan 02a §4.1).

The end-to-end claim that our cooperative lock keeps a *real* second CAN writer out of
the *real* robot connect path needs vcan or the rig, neither of which exists here, so
that acceptance is deferred — `test_real_hardware_reverify` skips with a reason until
`OPENARM_LOCK_REAL_FIXTURE` points at a rig capture, at which point it re-runs the
holder-report parse against the real bytes.

The hook mechanism itself is not deferred: `test_hook_parses_a_real_format_capture`
drives `reverify_from_fixture` over a capture produced by a real holder process here,
proving the hook re-verifies rather than being a stub. The two together are the honest
shape — the machinery is exercised, only the hardware bytes are pending.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.can.lock import reverify
from backend.can.lock.harness import HeldLockProcess
from backend.can.lock.paths import normalize_lock_path
from backend.can.lock.reverify import fixture_dir_from_env, reverify_from_fixture


def test_hook_parses_a_real_format_capture(tmp_path: Path) -> None:
    """The hook re-runs the holder parse over a genuine lock-file capture."""
    lock_dir = tmp_path / "live"
    lock_dir.mkdir()
    fixture_dir = tmp_path / "capture"
    fixture_dir.mkdir()

    with HeldLockProcess(str(lock_dir), ["can0"]) as holder:
        live = normalize_lock_path("can0", str(lock_dir))
        captured = normalize_lock_path("can0", str(fixture_dir))
        captured.write_bytes(live.read_bytes())
        (fixture_dir / "expected.json").write_text(
            json.dumps({"can0": {"holder_pid": holder.pid}}), encoding="utf-8"
        )

    results = reverify_from_fixture(fixture_dir)
    assert len(results) == 1
    assert results[0].matched, results[0].detail
    assert results[0].report.holder_pid is not None


def test_hook_reports_a_mismatch(tmp_path: Path) -> None:
    """A capture whose PID disagrees with the expectation is reported, not passed."""
    with HeldLockProcess(str(tmp_path), ["can0"]):
        captured = normalize_lock_path("can0", str(tmp_path))
        # Copy nothing extra; the live lock file already holds the real record.
        (tmp_path / "expected.json").write_text(
            json.dumps({"can0": {"holder_pid": -12345}}), encoding="utf-8"
        )
        results = reverify_from_fixture(tmp_path)
    assert results and not results[0].matched
    assert captured.name in {f.name for f in tmp_path.iterdir()}


@pytest.mark.skipif(
    fixture_dir_from_env() is None,
    reason=(
        "deferred: needs a real hardware/vcan lock capture; set OPENARM_LOCK_REAL_FIXTURE "
        "to a rig capture directory (captured openarm-<iface>.lock files + expected.json)"
    ),
)
def test_real_hardware_reverify() -> None:
    """Re-verify against a real rig capture, the moment one is supplied."""
    fixture_dir = fixture_dir_from_env()
    assert fixture_dir is not None
    results = reverify.reverify_from_fixture(fixture_dir)
    assert results, "real fixture directory declared no interfaces"
    for result in results:
        assert result.matched, f"{result.iface}: {result.detail}"
