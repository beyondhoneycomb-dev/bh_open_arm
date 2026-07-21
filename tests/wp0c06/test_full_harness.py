"""The full harness runs all seven conditions unattended and publishes a whole artifact.

This is the end-to-end acceptance run (①): one call produces the seven conditions with
no manual step, and the artifact carries every clause's evidence — the four load
params (②), the load-bites verdict (③), the computed GIL contribution (④), the RT
before/after with an honest applied flag (⑤), full per-condition distributions (⑥),
the measured self-overhead (⑦), and a provisional, non-verdict f_max_python (⑧) — with
connect() never called and the manifest clearing both barriers.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from registry.env.barrier import check_manifest as check_env
from registry.env.env_hash import read_issued as read_env_hash
from registry.normalization.barrier import check_manifest as check_normalization
from registry.normalization.content_hash import ISSUED_PATH as NORMALIZATION_ISSUED_PATH
from registry.normalization.content_hash import read_issued as read_normalization_hash
from sim.harness.artifact import build_artifact
from sim.harness.harness import run_harness
from sim.harness.load_profile import LoadProfile
from tests.wp0c06 import FAST_CONFIG


@pytest.fixture(scope="module")
def artifact() -> dict:
    """Run the full harness once at the fast config and build its artifact."""
    result = run_harness(LoadProfile(5, 320, 240, 32 * 1024, 128 * 1024), FAST_CONFIG)
    return build_artifact(result)


def test_all_seven_conditions_ran(artifact: dict) -> None:
    """Acceptance ① — the seven conditions are present, produced with no manual step."""
    assert [c["number"] for c in artifact["conditions"]] == [1, 2, 3, 4, 5, 6, 7]


def test_load_profile_recorded(artifact: dict) -> None:
    """Acceptance ② — the four load parameters are in the artifact."""
    profile = artifact["load_profile"]
    assert profile["stream_count"] == 5
    assert profile["resolution"] == [320, 240]
    assert profile["png_write_bytes_per_frame"] == 32 * 1024
    assert profile["serialize_bytes_per_tick"] == 128 * 1024


def test_load_bites(artifact: dict) -> None:
    """Acceptance ③ — the loaded distribution is distinguishable from idle."""
    assert artifact["load_distinguishability"]["distinguishable"]


def test_gil_contribution_computed(artifact: dict) -> None:
    """Acceptance ④ — the GIL contribution is a finite computed number."""
    assert math.isfinite(artifact["gil_contribution"]["gil_contribution_sec"])
    assert "comparison" in artifact["gil_contribution"]


def test_rt_before_after_published(artifact: dict) -> None:
    """Acceptance ⑤ — RT before/after is published with an honest applied flag."""
    condition_6 = next(c for c in artifact["conditions"] if c["number"] == 6)
    extra = condition_6["extra"]
    assert extra["rt_promotion"] is not None
    assert extra["before"]["raw_samples"] and extra["after"]["raw_samples"]
    assert math.isfinite(extra["median_gain_sec"])
    # The gain is only interpretable as RT when RT was actually applied.
    assert extra["gain_interpretable"] == extra["rt_promotion"]["applied"]


def test_full_histograms_published(artifact: dict) -> None:
    """Acceptance ⑥ — every timing condition carries its full distribution."""
    for condition in artifact["conditions"]:
        if condition["is_timing"]:
            distribution = condition["distribution"]
            assert distribution["raw_samples"]
            assert distribution["histogram"]["counts"]


def test_self_overhead_measured(artifact: dict) -> None:
    """Acceptance ⑦ — the harness self-overhead is measured and recorded."""
    overhead = artifact["self_overhead"]
    assert overhead["iterations"] > 0
    assert overhead["median"] >= 0.0


def test_no_numeric_verdict(artifact: dict) -> None:
    """Acceptance ⑧ — f_max_python is provisional and explicitly not a verdict."""
    fmax = artifact["fmax_python_provisional"]
    assert fmax["provisional"] is True
    assert fmax["is_verdict"] is False
    assert fmax["judged_by"] == "WP-1-04"
    assert fmax["canonical_gate"] == "PG-RT-001b"
    assert artifact["gate_status"] == "provisional"


def test_connect_never_called(artifact: dict) -> None:
    """The offline harness opened no rig session."""
    assert artifact["connect_call_count"] == 0


def test_manifest_clears_both_barriers(artifact: dict) -> None:
    """The stamped manifest clears the env and normalization launch barriers."""
    manifest = artifact["manifest"]
    env_issued = read_env_hash()
    norm_issued = read_normalization_hash(NORMALIZATION_ISSUED_PATH)
    assert env_issued is not None and norm_issued is not None
    assert not check_env(manifest, env_issued).blocked
    assert not check_normalization(manifest, norm_issued).blocked


def test_artifact_round_trips_through_json(artifact: dict, tmp_path: Path) -> None:
    """The built artifact is JSON-serializable and reloads unchanged in key fields."""
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    assert reloaded["wp_id"] == "WP-0C-06"
    assert reloaded["load_profile"] == artifact["load_profile"]
    assert len(reloaded["conditions"]) == 7


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
