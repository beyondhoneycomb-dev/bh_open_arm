"""Acceptance ⑦ and ⑧ — the bench is per-target runnable and nails no numeric target.

⑦ The harness runs for each of the four fleet targets and yields a per-target result
   that records where it was actually measured (NFR-TEL-004: an x86 number is not a
   fleet verdict).
⑧ It fixes no numeric pass/fail threshold — it emits measurements, and the CLI
   always exits 0 (it renders no verdict). Targets are sampled by FK round-trip, so
   no numeric target pose is nailed either.
"""

from __future__ import annotations

import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("lerobot")

from openarm_control.kinematics import IKParams

from sim.ik import bench
from targets.matrix import FLEET_TARGETS

_FAST = IKParams(max_iters=2, dt=0.1, damping=0.1, posture_cost=0.01, lm_damping=0.01)


def test_each_fleet_target_is_runnable() -> None:
    for target_id in FLEET_TARGETS:
        result = bench.run_target_bench(target_id, samples=3, seed=0, ik_params=_FAST)
        assert result.target_id == target_id
        assert result.samples == 3
        assert result.latency_ms_p50 is not None
        assert result.latency_ms_p99 is not None


def test_run_all_covers_the_four_targets() -> None:
    run = bench.run_all_targets(samples=2, seed=1, ik_params=_FAST)
    assert [result.target_id for result in run.results] == list(FLEET_TARGETS)


def test_provenance_is_recorded_not_fabricated() -> None:
    # This host is not a fleet target (targets/matrix.yaml), so every result must say
    # so rather than passing a local number off as the target's.
    run = bench.run_all_targets(samples=2, seed=2, ik_params=_FAST)
    for result in run.results:
        assert result.measured_on_target is False
        assert result.note != ""
        assert "NFR-TEL-004" in result.note


def test_unknown_target_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown fleet target"):
        bench.run_target_bench("a100", samples=1)


def test_seeded_targets_are_reproducible() -> None:
    adapter = bench.build_ik_adapter(ik_params=_FAST)
    first = bench.sample_reachable_targets(adapter, count=4, seed=7)
    second = bench.sample_reachable_targets(adapter, count=4, seed=7)
    for (right_a, left_a), (right_b, left_b) in zip(first, second, strict=True):
        assert (right_a == right_b).all()
        assert (left_a == left_b).all()


def test_cli_renders_no_verdict_and_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = bench.main(["--target", "rtx_5090", "--samples", "2", "--seed", "0"])
    assert exit_code == 0
    out = capsys.readouterr().out
    import json

    record = json.loads(out)
    assert record["results"][0]["target_id"] == "rtx_5090"
