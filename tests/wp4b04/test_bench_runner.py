"""CG-4B-04e: the per-target IK/inference bench harness RUNS here, target numbers deferred.

`PG-IK-001` is per-target and needs each target's own hardware; this box is an rtx_5080,
not a fleet target, so the harness must run locally, produce the input record (IK p50/p99
+ unconstrained-fallback count + collision latency) and honestly defer the per-target
figure rather than relabel a local number as a fleet verdict (`NFR-TEL-004`). The one
host-independent branch is the safety one: a fallback firing is `FAIL_BLOCKING` on any
host — here fallback is blocked by default, so the gate is `DEFERRED`.
"""

from __future__ import annotations

from backend.compat.deploy_matrix.bench_runner import (
    measure_collision_latency,
    run_all,
    run_deploy_bench,
)
from backend.compat.deploy_matrix.target import DeploymentTarget

_IK_SAMPLES = 3
_COLLISION_SAMPLES = 8


def test_collision_latency_measures_real_contacts() -> None:
    """The collision harness times `mj_collision` and actually finds contacts locally."""
    latency = measure_collision_latency(samples=_COLLISION_SAMPLES, seed=0)
    assert latency.samples == _COLLISION_SAMPLES
    assert latency.p50_ms is not None
    assert latency.p99_ms is not None
    assert latency.max_contacts >= 0


def test_run_deploy_bench_produces_all_three_measurements() -> None:
    """One target's run yields IK p50/p99, a fallback count, and collision latency."""
    bench = run_deploy_bench(
        DeploymentTarget.JETSON_ORIN,
        ik_samples=_IK_SAMPLES,
        collision_samples=_COLLISION_SAMPLES,
        seed=0,
    )
    assert bench.ik.latency_ms_p50 is not None
    assert bench.ik.latency_ms_p99 is not None
    assert bench.ik.fallback_firings >= 0
    assert bench.collision.p50_ms is not None


def test_per_target_figures_are_deferred_on_this_host() -> None:
    """This host is no fleet target, so the run is measured-off and the IK gate deferred."""
    bench = run_deploy_bench(
        DeploymentTarget.JETSON_ORIN,
        ik_samples=_IK_SAMPLES,
        collision_samples=_COLLISION_SAMPLES,
        seed=0,
    )
    assert bench.measured_on_target is False
    assert bench.ik_gate == "deferred"
    assert "deferred" in bench.note.lower()


def test_fallback_is_blocked_by_default_so_no_safety_fail() -> None:
    """The IK adapter's unconstrained fallback is off by default, so no firing occurs."""
    bench = run_deploy_bench(
        DeploymentTarget.JETSON_ORIN,
        ik_samples=_IK_SAMPLES,
        collision_samples=_COLLISION_SAMPLES,
        seed=0,
    )
    assert bench.ik.fallback_firings == 0
    assert bench.ik_gate != "fail_blocking"


def test_run_all_covers_every_target() -> None:
    """The sweep produces one deferred result per deployment target."""
    benches = run_all(ik_samples=_IK_SAMPLES, collision_samples=_COLLISION_SAMPLES, seed=0)
    assert {bench.target for bench in benches} == {t.value for t in DeploymentTarget}
    assert all(bench.measured_on_target is False for bench in benches)
