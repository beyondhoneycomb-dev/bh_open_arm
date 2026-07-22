"""WP-2B-03 deferred re-verification hook: a real capture re-runs the identical verification.

The hook is what the deferral ships. It reads the measured torque only from the capture file —
never from the model it validates — and forces the REAL basis, so it cannot manufacture a green
(no self-approval). A real capture yields a non-provisional report; a missing or empty capture
is refused rather than defaulted.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.gravity import GravityBackend
from backend.gravity_verify.measurement import MeasurementBasis
from backend.gravity_verify.reverify import (
    FIXTURE_ENV_VAR,
    fixture_dir_from_env,
    reverify_from_fixture,
)


def _write_capture(directory: Path, name: str, grid: list[dict[str, list[float]]]) -> None:
    """Write one capture JSON file with a `samples` list of `{q, tau_meas}`."""
    (directory / name).write_text(json.dumps({"samples": grid}), encoding="utf-8")


def test_fixture_dir_from_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """With the env var unset the hook reports no fixture (deferred, not failed)."""
    monkeypatch.delenv(FIXTURE_ENV_VAR, raising=False)
    assert fixture_dir_from_env() is None


def test_fixture_dir_from_env_points_at_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A set env var pointing at a real directory is returned."""
    monkeypatch.setenv(FIXTURE_ENV_VAR, str(tmp_path))
    assert fixture_dir_from_env() == tmp_path


def test_reverify_runs_identical_verification_on_real_capture(
    backend: GravityBackend, pose_grid: tuple[tuple[float, ...], ...], tmp_path: Path
) -> None:
    """A real capture is verified on the REAL basis and the report is not provisional."""
    samples = [{"q": list(pose), "tau_meas": list(backend.tau_grav(pose))} for pose in pose_grid]
    _write_capture(tmp_path, "session_a.json", samples)
    reports = reverify_from_fixture(tmp_path)
    assert len(reports) == 1
    assert reports[0].basis is MeasurementBasis.REAL
    assert reports[0].provisional is False
    assert reports[0].as_record()["deferred"]["awaited_inputs"] == []


def test_reverify_reads_torque_only_from_the_file(backend: GravityBackend, tmp_path: Path) -> None:
    """The measured torque is the file's, not the model's — a nonzero residual survives.

    If the hook re-derived tau_meas from the model it validates, this residual would collapse to
    zero (self-approval). Because the torque comes from the capture, the injected offset stands.
    """
    pose = (0.3, 1.2, -0.4, 0.8, 0.2, -0.3, 0.1)
    model = backend.tau_grav(pose)
    measured = [model[j] + 1.25 for j in range(7)]
    _write_capture(tmp_path, "offset.json", [{"q": list(pose), "tau_meas": measured}])
    report = reverify_from_fixture(tmp_path)[0]
    for stat in report.residual_table.joint_stats:
        assert stat.max_abs_nm == pytest.approx(1.25, abs=1e-9)


def test_reverify_empty_directory_is_refused(tmp_path: Path) -> None:
    """A directory with no captures is a FileNotFoundError, never a fabricated green."""
    with pytest.raises(FileNotFoundError):
        reverify_from_fixture(tmp_path)


def test_reverify_empty_capture_is_refused(tmp_path: Path) -> None:
    """A capture with no samples is refused rather than yielding an empty verdict."""
    _write_capture(tmp_path, "empty.json", [])
    with pytest.raises(ValueError, match="no samples"):
        reverify_from_fixture(tmp_path)
