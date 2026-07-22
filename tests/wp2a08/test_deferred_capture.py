"""DEFERRED — the physical open/close endpoint capture, honestly skipped (`02a` §4.1).

The physical capture needs an operator and a live DM4310, neither present on this dev
host, so `test_real_hardware_capture_is_deferred` skips with a reason until
`OPENARM_GRIPPER_REAL_FIXTURE` points at a captured record. The hook machinery is not
deferred: the offline tests drive `reverify_from_fixture` over synthetic-format
captures and prove it re-runs build-and-validate — reporting a match for a config that
loads and a mismatch for one that is refused — rather than being a stub. The two
together are the honest shape: the machinery is green here, only the physical bytes
are pending.
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
    """The deferred acceptance ships a real-fixture hook, per plan `02a` §4.1."""
    assert hasattr(reverify, "reverify_from_fixture")
    assert reverify.FIXTURE_ENV_VAR == "OPENARM_GRIPPER_REAL_FIXTURE"


@pytest.mark.skipif(
    fixture_dir_from_env() is None,
    reason=(
        "deferred: needs an operator to place the gripper at the physical open/close "
        "stops and a live DM4310 to read native rad; set OPENARM_GRIPPER_REAL_FIXTURE "
        "to a directory holding record.json + expected.json from a real capture"
    ),
)
def test_real_hardware_capture_is_deferred() -> None:
    """Re-verify a real captured record the moment a fixture directory is supplied."""
    fixture_dir = fixture_dir_from_env()
    assert fixture_dir is not None
    results = reverify_from_fixture(fixture_dir)
    assert results, "real fixture directory held no capture"
    for result in results:
        assert result.matched, result.detail
