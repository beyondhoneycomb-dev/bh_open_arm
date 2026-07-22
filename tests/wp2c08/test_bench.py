"""Per-target latency bench: real host numbers, deferred target verdicts, honest re-verify.

THE ONE RULE here is that no target is ever asserted green from an x86 figure: the four
target slots stay DEFERRED, and the real numbers only ever come from the on-target
re-verification hook.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.collision_preflight.bench import (
    build_preflight_bench_artifact,
    nearest_rank_percentile,
    summarize_latencies,
)
from backend.collision_preflight.constants import (
    BENCH_TARGETS,
    TARGET_STATUS_DEFERRED,
)
from backend.collision_preflight.model import PreflightModel
from backend.collision_preflight.reverify import (
    fixture_dir_from_env,
    reverify_from_fixture,
)
from backend.safety_bringup.constants import COLLISION_MARGIN_DEFAULT_M


def _small_trajectory(model: PreflightModel) -> tuple[tuple[float, ...], ...]:
    return tuple(model.qpos_from_arms((0.01 * step,) + (0.0,) * 6, (0.0,) * 7) for step in range(4))


def test_bench_records_real_host_latency(preflight_model: PreflightModel) -> None:
    artifact = build_preflight_bench_artifact(
        _small_trajectory(preflight_model), margin_m=COLLISION_MARGIN_DEFAULT_M, repeats=2
    )
    host = artifact["host_reference"]["latency"]
    assert host["sample_count"] == 8
    assert host["percentiles_ms"]["p99"] >= 0.0


def test_all_four_targets_are_deferred(preflight_model: PreflightModel) -> None:
    artifact = build_preflight_bench_artifact(
        _small_trajectory(preflight_model), margin_m=COLLISION_MARGIN_DEFAULT_M, repeats=1
    )
    targets = artifact["targets"]
    assert {row["target"] for row in targets} == set(BENCH_TARGETS)
    # THE ONE RULE: no target verdict is fabricated from the host figure.
    for row in targets:
        assert row["status"] == TARGET_STATUS_DEFERRED
        assert row["latency"] is None
        assert row["status"] != "PASS"


def test_deferred_manifest_names_the_hook(preflight_model: PreflightModel) -> None:
    artifact = build_preflight_bench_artifact(
        _small_trajectory(preflight_model), margin_m=COLLISION_MARGIN_DEFAULT_M, repeats=1
    )
    deferred = artifact["deferred"]
    assert deferred["reverification_hook"] == (
        "backend.collision_preflight.reverify.reverify_from_fixture"
    )
    assert deferred["fixture_env_var"]


def test_nearest_rank_percentile() -> None:
    samples = (1.0, 2.0, 3.0, 4.0)
    assert nearest_rank_percentile(samples, 50.0) == 2.0
    assert nearest_rank_percentile(samples, 99.0) == 4.0
    assert nearest_rank_percentile((), 50.0) == 0.0


def test_reverify_summarizes_on_target_capture(tmp_path: Path) -> None:
    capture = {"target": "jetson_orin", "samples_ms": [1.0, 2.0, 3.0, 4.0, 5.0]}
    (tmp_path / "orin.json").write_text(json.dumps(capture), encoding="utf-8")
    results = reverify_from_fixture(tmp_path)
    assert len(results) == 1
    verified = results[0]
    assert verified.target == "jetson_orin"
    assert verified.refusal == ""
    assert verified.summary is not None
    assert verified.summary.sample_count == 5


def test_reverify_refuses_unknown_target(tmp_path: Path) -> None:
    (tmp_path / "bad.json").write_text(
        json.dumps({"target": "rtx_4090", "samples_ms": [1.0]}), encoding="utf-8"
    )
    results = reverify_from_fixture(tmp_path)
    assert results[0].summary is None
    assert "not one of the fleet targets" in results[0].refusal


def test_reverify_refuses_empty_capture(tmp_path: Path) -> None:
    (tmp_path / "empty.json").write_text(
        json.dumps({"target": "rtx_5090", "samples_ms": []}), encoding="utf-8"
    )
    results = reverify_from_fixture(tmp_path)
    assert results[0].summary is None
    assert "no samples" in results[0].refusal


def test_reverify_empty_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        reverify_from_fixture(tmp_path)


def test_fixture_dir_absent_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENARM_COLLISION_PREFLIGHT_REAL_FIXTURE", raising=False)
    assert fixture_dir_from_env() is None


def test_summarize_latencies_reports_all_percentiles() -> None:
    summary = summarize_latencies((1.0, 2.0, 3.0))
    assert summary.sample_count == 3
    assert set(summary.percentiles_ms) == {50.0, 95.0, 99.0}
