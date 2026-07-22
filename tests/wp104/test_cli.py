"""Acceptance ①: the offline orchestrator auto-runs the whole measurement and publishes.

`python -m backend.rtbench.cli` drives the synthetic harness (conditions 1-7, no manual
step), opens the single torque-OFF lock-held session, and writes the WP-1-04 artifact —
provisional by construction, with the real-CAN inputs left declared-as-deferred.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.rtbench.cli import main


def test_cli_runs_end_to_end_and_writes_a_provisional_artifact(tmp_path: Path) -> None:
    out = tmp_path / "artifact.json"
    lock_dir = tmp_path / "lock"
    lock_dir.mkdir()
    exit_code = main(
        [
            "--tick-count",
            "120",
            "--target-hz",
            "250",
            "--host-id",
            "dev-x86",
            "--lock-dir",
            str(lock_dir),
            "--out",
            str(out),
        ]
    )
    assert exit_code == 0

    artifact = json.loads(out.read_text(encoding="utf-8"))
    assert artifact["wp_id"] == "WP-1-04"
    assert artifact["gate_status"] == "provisional"
    assert artifact["stale_on"] == ["PG-RT-001b:PASS"]
    assert artifact["session"]["connect_call_count"] == 1
    assert [c["number"] for c in artifact["synthetic_run"]["conditions"]] == [1, 2, 3, 4, 5, 6, 7]
    assert artifact["target_host"]["is_fleet_target"] is False
    assert artifact["deferred"]["awaited_inputs"]
