"""WP-ENV-02 — the FR-INF-033/034 runtime guard predicates block and allow correctly."""

from __future__ import annotations

from targets.guards import orin_trt_backbone_unsupported, sync_over_inference_ceiling


def test_orin_trt_full_pipeline_is_blocked() -> None:
    decision = orin_trt_backbone_unsupported(
        {"target_id": "jetson_orin", "optimization_path": "trt_full_pipeline"}
    )
    assert decision.blocked


def test_non_orin_full_pipeline_is_allowed() -> None:
    decision = orin_trt_backbone_unsupported(
        {"target_id": "rtx_5090", "optimization_path": "trt_full_pipeline"}
    )
    assert not decision.blocked


def test_sync_above_ceiling_is_blocked() -> None:
    decision = sync_over_inference_ceiling(
        {"target_id": "jetson_orin", "policy_family": "groot", "fps": 30, "mode": "sync"}
    )
    assert decision.blocked


def test_sync_below_ceiling_is_allowed() -> None:
    decision = sync_over_inference_ceiling(
        {"target_id": "jetson_orin", "policy_family": "groot", "fps": 4, "mode": "sync"}
    )
    assert not decision.blocked


def test_rtc_mode_bypasses_the_ceiling() -> None:
    decision = sync_over_inference_ceiling(
        {"target_id": "jetson_orin", "policy_family": "groot", "fps": 30, "mode": "rtc"}
    )
    assert not decision.blocked


def test_unmeasured_pair_is_not_silently_blocked() -> None:
    decision = sync_over_inference_ceiling(
        {"target_id": "rtx_5090", "policy_family": "groot", "fps": 999, "mode": "sync"}
    )
    assert not decision.blocked
