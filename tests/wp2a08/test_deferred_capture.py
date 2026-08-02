"""The endpoint-capture re-verification hook, exercised offline end to end.

`backend.gripper_endpoint.reverify` exists for a build whose tool puts a motor on CAN
`0x08`. The rig's default tool does not, so there is no acceptance here that a gripper
must be placed at its physical stops — the tool registry is open and the hook is what a
future gripper needs, not a pending obligation on this bench.

Everything the hook does apart from producing the bytes runs here: the environment
discovery path, the rebuild through the same `from_json_dict` a normal load uses, and the
verdict for both a record that loads and one that is refused. A real capture is therefore
one environment variable away from being judged, with no code change.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.gripper_endpoint import reverify
from backend.gripper_endpoint.reverify import fixture_dir_from_env, reverify_from_fixture
from tests.wp2a08.conftest import RIGHT_HI_RAD, RIGHT_LO_RAD, make_record


def _write_fixture(
    fixture_dir: Path, record_payload: dict[str, object], expect_loads: bool
) -> None:
    """Write a `record.json` + `expected.json` pair into a fixture directory."""
    (fixture_dir / "record.json").write_text(json.dumps(record_payload), encoding="utf-8")
    (fixture_dir / "expected.json").write_text(
        json.dumps({"loads": expect_loads}), encoding="utf-8"
    )


def test_hook_reverifies_a_matching_capture(tmp_path: Path) -> None:
    """A captured record that loads, expected to load, is reported as a match."""
    _write_fixture(tmp_path, make_record().to_json_dict(), expect_loads=True)

    results = reverify_from_fixture(tmp_path)
    assert len(results) == 1
    assert results[0].matched, results[0].detail
    assert results[0].loaded


def test_hook_reports_an_unmirrored_capture(tmp_path: Path) -> None:
    """A capture whose left limits are not mirrored is refused, and the mismatch shows."""
    payload = make_record().to_json_dict()
    payload["left_limits"]["lo_rad"] = RIGHT_LO_RAD
    payload["left_limits"]["hi_rad"] = RIGHT_HI_RAD
    payload.pop("checksum", None)
    _write_fixture(tmp_path, payload, expect_loads=True)

    results = reverify_from_fixture(tmp_path)
    assert results and not results[0].matched
    assert not results[0].loaded
    assert "sign-mirror" in results[0].detail


def test_reverification_hook_is_wired() -> None:
    """The hook ships the shape plan `02a` §4.1 requires of a re-verification path."""
    assert hasattr(reverify, "reverify_from_fixture")
    assert reverify.FIXTURE_ENV_VAR == "OPENARM_GRIPPER_REAL_FIXTURE"


def test_hook_judges_the_directory_the_environment_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The environment variable is the whole discovery path a real capture travels."""
    _write_fixture(tmp_path, make_record().to_json_dict(), expect_loads=True)
    monkeypatch.setenv(reverify.FIXTURE_ENV_VAR, str(tmp_path))

    fixture_dir = fixture_dir_from_env()
    assert fixture_dir == tmp_path
    results = reverify_from_fixture(fixture_dir)
    assert results and results[0].matched, results[0].detail


def test_hook_finds_no_directory_when_the_environment_is_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unset variable yields None rather than a path that would read the repo root."""
    monkeypatch.delenv(reverify.FIXTURE_ENV_VAR, raising=False)
    assert fixture_dir_from_env() is None
