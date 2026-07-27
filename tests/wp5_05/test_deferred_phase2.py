"""Phase-2 (real-camera occupancy) is deferred honestly — skipped with a reason, not faked.

Phase-2 is AI-on-HW and there is no camera on this host. The hook must skip with a
reason when no fixture is set, refuse a missing file, and only actually ingest an
occupancy record when a real capture is supplied.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.loadtest.constants import PHASE2_FIXTURE_ENV_VAR
from backend.loadtest.reverify import reverify_phase2_from_fixture


def test_unset_fixture_skips_with_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(PHASE2_FIXTURE_ENV_VAR, raising=False)
    status = reverify_phase2_from_fixture()
    assert status.ran is False
    assert "deferred" in status.reason
    assert status.occupancy is None


def test_missing_file_is_reported_not_silently_passed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(PHASE2_FIXTURE_ENV_VAR, str(tmp_path / "does_not_exist.json"))
    status = reverify_phase2_from_fixture()
    assert status.ran is False
    assert "not a file" in status.reason


def test_present_fixture_is_ingested(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    capture = tmp_path / "occupancy.json"
    capture.write_text(json.dumps({"node_occupancy_pct": 42.0}), encoding="utf-8")
    monkeypatch.setenv(PHASE2_FIXTURE_ENV_VAR, str(capture))
    status = reverify_phase2_from_fixture()
    assert status.ran is True
    assert status.occupancy == {"node_occupancy_pct": 42.0}
