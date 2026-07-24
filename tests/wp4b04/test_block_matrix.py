"""The block matrix enforces the SPINE §7 deployment table per (target, policy, fps).

Covers CG-4B-04a (Orin + GR00T = 4.6 Hz sourced; fps>4.6 -> sync blocked + RTC/async
required) and CG-4B-04b (Orin, any policy -> trt_full_pipeline blocked, DiT-only allowed),
plus the shape `02c` §2.4 calls the WP's core: a target-gate failure is that target's
mark, not a global one — so the same policy is open on an RTX target and blocked on a
Jetson one at the same fps. The IK gate is `DEFERRED` on this AI-offline band.
"""

from __future__ import annotations

from backend.compat.deploy_matrix.block_matrix import (
    DEFAULT_FPS,
    IkGateStatus,
    Optimization,
    evaluate,
    evaluate_fleet,
    policy_axis,
)
from backend.compat.deploy_matrix.target import DeploymentTarget
from backend.inference.adapter.backend_kind import InferenceBackend


def test_cg_4b_04a_orin_groot_sync_blocked_over_ceiling() -> None:
    """CG-4B-04a: Orin + GR00T at 30 fps -> expected_hz 4.6, sync blocked, RTC/async."""
    verdict = evaluate(DeploymentTarget.JETSON_ORIN, "groot", fps=30.0)
    assert verdict.expected_hz == 4.6
    assert "11 §2.6" in verdict.expected_hz_source
    assert InferenceBackend.SYNC in verdict.blocked_backends
    assert set(verdict.required_alternatives) == {
        InferenceBackend.RTC,
        InferenceBackend.REMOTE_GRPC,
    }
    assert any(reason.code == "FR-INF-034" for reason in verdict.reasons)


def test_orin_groot_sync_allowed_at_or_below_ceiling() -> None:
    """At fps <= the 4.6 Hz ceiling, sync is not blocked (the ceiling is a real bound)."""
    verdict = evaluate(DeploymentTarget.JETSON_ORIN, "groot", fps=4.0)
    assert InferenceBackend.SYNC not in verdict.blocked_backends
    assert verdict.required_alternatives == ()


def test_cg_4b_04b_orin_any_policy_blocks_trt_full_allows_dit_only() -> None:
    """CG-4B-04b: on Orin, every policy blocks trt_full_pipeline but not DiT-only."""
    for policy in policy_axis():
        verdict = evaluate(DeploymentTarget.JETSON_ORIN, policy, fps=DEFAULT_FPS)
        assert Optimization.TRT_FULL_PIPELINE in verdict.blocked_optimizations
        assert Optimization.TRT_DIT_ONLY not in verdict.blocked_optimizations
        assert any(reason.code.startswith("FR-INF-033") for reason in verdict.reasons)


def test_nano_conservative_blocks_without_a_sourced_ceiling() -> None:
    """Jetson Nano (unknown ceiling) blocks sync conservatively and trt_full too."""
    verdict = evaluate(DeploymentTarget.JETSON_NANO, "groot", fps=30.0)
    assert verdict.expected_hz is None
    assert InferenceBackend.SYNC in verdict.blocked_backends
    assert Optimization.TRT_FULL_PIPELINE in verdict.blocked_optimizations


def test_rtx_targets_are_unblocked_by_default() -> None:
    """RTX 5090/A6000 impose no backend or optimization block (self-bench determines)."""
    for target in (DeploymentTarget.RTX_5090, DeploymentTarget.RTX_A6000):
        verdict = evaluate(target, "groot", fps=30.0)
        assert verdict.blocked_backends == ()
        assert verdict.blocked_optimizations == ()
        assert verdict.reasons == ()


def test_target_gate_failure_is_scoped_to_that_target() -> None:
    """The same policy/fps is open on RTX and blocked on Jetson — no global failure."""
    rtx = evaluate(DeploymentTarget.RTX_5090, "groot", fps=30.0)
    jetson = evaluate(DeploymentTarget.JETSON_ORIN, "groot", fps=30.0)
    assert rtx.blocked_backends == ()
    assert InferenceBackend.SYNC in jetson.blocked_backends


def test_ik_gate_is_deferred_on_offline_band() -> None:
    """The per-target PG-IK-001 verdict needs target hardware, so it is DEFERRED here."""
    verdict = evaluate(DeploymentTarget.JETSON_ORIN, "groot")
    assert verdict.ik_gate is IkGateStatus.DEFERRED


def test_evaluate_fleet_covers_every_target_and_policy() -> None:
    """The fleet sweep renders one verdict per (target, policy), all four targets present."""
    verdicts = evaluate_fleet()
    seen_targets = {verdict.target for verdict in verdicts}
    assert seen_targets == set(DeploymentTarget)
    assert len(verdicts) == len(DeploymentTarget) * len(policy_axis())
