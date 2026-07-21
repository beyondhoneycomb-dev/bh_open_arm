"""Acceptance ⑦ — the real-fixture re-verification hook (plan 02a §4.1).

The claim that the parser reads a *real adapter's* `ip -details link show` correctly needs
hardware, which does not exist here, so `test_real_hardware_reverify` skips with a reason
until `OPENARM_LINK_REAL_FIXTURE` points at a capture directory. The hook machinery is not
deferred: `test_hook_reverifies_a_capture` drives it over a real-format capture, proving
it re-runs parse-and-validate rather than being a stub. The two together are the honest
shape — the machinery is exercised, only the hardware bytes are pending.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.can.link import reverify
from backend.can.link.reverify import fixture_dir_from_env, reverify_from_fixture

_CORPUS = Path(__file__).resolve().parent / "fixtures" / "corpus"


def test_hook_reverifies_a_capture(tmp_path: Path) -> None:
    """The hook re-runs the pipeline over a capture and confirms the expectation."""
    (tmp_path / "can0.txt").write_bytes((_CORPUS / "normal.txt").read_bytes())
    (tmp_path / "expected.json").write_text(
        json.dumps(
            {
                "can0": {
                    "ok": True,
                    "state": "ERROR-ACTIVE",
                    "fd": True,
                    "bitrate": 1000000,
                    "dbitrate": 5000000,
                }
            }
        ),
        encoding="utf-8",
    )

    results = reverify_from_fixture(tmp_path)
    assert len(results) == 1
    assert results[0].matched, results[0].detail
    assert results[0].verdict.ok


def test_hook_reports_a_mismatch(tmp_path: Path) -> None:
    """A capture whose verdict disagrees with the expectation is reported, not passed."""
    (tmp_path / "can0.txt").write_bytes((_CORPUS / "bus_off.txt").read_bytes())
    (tmp_path / "expected.json").write_text(json.dumps({"can0": {"ok": True}}), encoding="utf-8")

    results = reverify_from_fixture(tmp_path)
    assert results and not results[0].matched


@pytest.mark.skipif(
    fixture_dir_from_env() is None,
    reason=(
        "deferred: needs a real hardware/vcan `ip -details link show` capture; set "
        "OPENARM_LINK_REAL_FIXTURE to a directory of <iface>.txt captures + expected.json"
    ),
)
def test_real_hardware_reverify() -> None:
    """Re-verify against a real adapter capture, the moment one is supplied."""
    fixture_dir = fixture_dir_from_env()
    assert fixture_dir is not None
    results = reverify.reverify_from_fixture(fixture_dir)
    assert results, "real fixture directory declared no interfaces"
    for result in results:
        assert result.matched, f"{result.iface}: {result.detail}"
