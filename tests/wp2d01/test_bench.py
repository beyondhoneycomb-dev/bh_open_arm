"""Acceptance ⑦ — the jog latency bench is per-target runnable and nails no threshold.

PG-IK-001 is per-target (03 §5.11): the bench runs for each of the four fleet targets
and records where it was actually measured. On this host every target is deferred — an
rtx_5080 is not one of the four — and the harness says so (NFR-TEL-004) rather than
passing a local number off as a fleet verdict. It fixes no numeric pass/fail; the CLI
exits 0 because it renders measurements, not a verdict.
"""

from __future__ import annotations

import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("lerobot")

from openarm_control.kinematics import IKParams

from backend.cartesian_jog import bench
from targets.matrix import FLEET_TARGETS

_FAST = IKParams(max_iters=2, dt=0.1, damping=0.1, posture_cost=0.01, lm_damping=0.01)


def test_each_fleet_target_is_runnable() -> None:
    for target_id in FLEET_TARGETS:
        result = bench.run_target_bench(target_id, steps=4, seed=0, ik_params=_FAST)
        assert result.target_id == target_id
        assert result.steps == 4
        assert result.latency_ms_p50 is not None
        assert result.latency_ms_p99 is not None
        assert result.committed + result.held == 4


def test_run_all_covers_the_four_targets() -> None:
    run = bench.run_all_targets(steps=3, seed=1, ik_params=_FAST)
    assert [result.target_id for result in run.results] == list(FLEET_TARGETS)


def test_provenance_is_recorded_not_fabricated() -> None:
    run = bench.run_all_targets(steps=2, seed=2, ik_params=_FAST)
    for result in run.results:
        assert result.measured_on_target is False
        assert result.note != ""
        assert "NFR-TEL-004" in result.note


def test_unknown_target_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown fleet target"):
        bench.run_target_bench("a100", steps=1)


def test_cli_renders_measurements_and_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    import json

    exit_code = bench.main(["--target", "rtx_5090", "--steps", "2"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    # A measurement record, with no pass/fail verdict field anywhere in it.
    assert payload["results"][0]["target_id"] == "rtx_5090"
    assert "verdict" not in payload
    assert "pass" not in payload
