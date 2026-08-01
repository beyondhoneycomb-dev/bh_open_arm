"""What may and may not reach the operator's capture tree.

Every hook here nests its numbers one or two objects deep, so the out-of-scope-measurement
refusal is judged over the whole payload rather than its top level: the top-level shape is the
one nobody would actually write.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from scripts import torque_session as session


def _measured(payload: dict[str, Any]) -> session.Measurement:
    """A measurement carrying the given payload, marked as coming off the rig."""
    return session.Measurement(source=session.SOURCE_MEASURED, name="capture", payload=payload)


def _engage_step() -> session.Step:
    """The step whose capture tree the refusals are exercised against."""
    return session.STEP_BY_NUMBER[1]


def test_a_top_level_stop_latency_key_is_refused(tmp_path: Path) -> None:
    payload = {"host_id": "h", session.STOP_LATENCY_KEY: {"samples_sec": [0.01]}}
    with pytest.raises(session.SessionRefusedError, match=session.STOP_LATENCY_KEY):
        session.write_capture(_engage_step(), _measured(payload), tmp_path)


def test_a_nested_stop_latency_key_is_refused(tmp_path: Path) -> None:
    payload = {
        "host_id": "h",
        "engage": {"send_ids": [1], session.STOP_LATENCY_KEY: {"samples_sec": [0.01]}},
    }
    with pytest.raises(session.SessionRefusedError, match=session.STOP_LATENCY_KEY):
        session.write_capture(_engage_step(), _measured(payload), tmp_path)


def test_a_stop_latency_key_inside_a_list_is_refused(tmp_path: Path) -> None:
    payload = {"host_id": "h", "runs": [{session.STOP_LATENCY_KEY: {"samples_sec": [0.01]}}]}
    with pytest.raises(session.SessionRefusedError, match=session.STOP_LATENCY_KEY):
        session.write_capture(_engage_step(), _measured(payload), tmp_path)


def test_a_stop_latency_key_inside_a_tuple_is_refused(tmp_path: Path) -> None:
    payload = {"host_id": "h", "runs": ({session.STOP_LATENCY_KEY: {"samples_sec": [0.01]}},)}
    with pytest.raises(session.SessionRefusedError, match=session.STOP_LATENCY_KEY):
        session.write_capture(_engage_step(), _measured(payload), tmp_path)


def test_a_synthetic_payload_never_reaches_the_capture_tree(tmp_path: Path) -> None:
    synthetic = session._synthetic_torque_bringup()
    with pytest.raises(session.SessionRefusedError, match=session.SOURCE_SYNTHETIC):
        session.write_capture(_engage_step(), synthetic, tmp_path)
    assert not list(tmp_path.rglob("*.json"))


def test_a_refused_payload_leaves_no_file_behind(tmp_path: Path) -> None:
    payload = {"host_id": "h", "engage": {session.STOP_LATENCY_KEY: {}}}
    with pytest.raises(session.SessionRefusedError):
        session.write_capture(_engage_step(), _measured(payload), tmp_path)
    assert not list(tmp_path.rglob("*.json"))


def test_a_payload_the_hook_refuses_never_reaches_the_capture_tree(tmp_path: Path) -> None:
    """The hook judges before the write, not after it.

    Judged with a payload the writer's own two refusals let through — it is marked measured and
    carries no out-of-scope key — so the only thing that can stop it is the WP-1-05 hook loading
    it and objecting. A file written first and judged second leaves a capture in the operator's
    tree that fails months later inside a pytest run, which is the arrangement this ordering
    exists to prevent.
    """
    wider = session._synthetic_torque_bringup(extra_motor=True)
    measured = session.Measurement(
        source=session.SOURCE_MEASURED, name=wider.name, payload=wider.payload
    )
    with pytest.raises(session.SessionRefusedError):
        session.write_capture(_engage_step(), measured, tmp_path)
    assert not list(tmp_path.rglob("*.json"))


def test_a_state_file_survives_a_write_that_failed_halfway(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`--status` reads this file, so a half-written one reports a session that never happened."""
    path = tmp_path / session.STATE_FILENAME
    session._atomic_write_json(path, {"steps": {"engage": {"passed": True}}})
    recorded = path.read_text(encoding="utf-8")

    def _explode(_descriptor: int) -> None:
        raise OSError("the disk went away mid-write")

    monkeypatch.setattr(os, "fsync", _explode)
    with pytest.raises(OSError, match="mid-write"):
        session._atomic_write_json(path, {"steps": {"engage": {"passed": False}}})
    assert path.read_text(encoding="utf-8") == recorded
    assert list(tmp_path.iterdir()) == [path]
