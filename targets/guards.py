"""Executable per-target runtime guards (`11` FR-INF-033/034).

`matrix.yaml`'s `blocked_paths[]` are not prose: each names one of these callables,
and `targets.matrix` refuses a matrix whose blocked path points at a name that does
not resolve to a guard here (WP-ENV-02 acceptance ③). The guards are pure and
stdlib-only — a runtime layer calls them with a context and must not proceed on a
`blocked` decision.

  * FR-INF-033 — Jetson Orin's TRT 10.3 cannot compile the backbone engine, so the
    `trt_full_pipeline` optimisation path is blocked; only DiT-only is allowed.
  * FR-INF-034 — the expected inference frequency of a hardware/policy pair caps
    synchronous inference; an `fps` above the ceiling must switch to RTC / async
    chunking (Jetson Orin + GR00T = 4.6 Hz, `11` §2.6).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# `11` §2.6 — measured policy-forward ceilings, keyed by (target_id, policy_family).
# The set is intentionally small: it is the evidence table FR-INF-034 cites, not a
# guess. A pair absent from the table has no measured ceiling and is not blocked by
# frequency here — that is a missing measurement, reported, never a silent pass.
INFERENCE_CEILING_HZ: dict[tuple[str, str], float] = {
    ("jetson_orin", "groot"): 4.6,
    ("jetson_nano", "groot"): 4.6,
}

TRT_FULL_PIPELINE = "trt_full_pipeline"
ORIN_TARGET = "jetson_orin"
SYNC_MODE = "sync"


@dataclass(frozen=True)
class GuardDecision:
    """The outcome of evaluating one guard against a context.

    Attributes:
        blocked: True when the runtime layer must not take this path.
        reason: Why, for the operator-facing report; empty when allowed.
    """

    blocked: bool
    reason: str


def orin_trt_backbone_unsupported(context: dict[str, Any]) -> GuardDecision:
    """FR-INF-033 — block `trt_full_pipeline` on Jetson Orin (TRT 10.3 backbone gap).

    Args:
        context: `{target_id, optimization_path}`.

    Returns:
        (GuardDecision) Blocked on Orin + full-pipeline TRT, else allowed.
    """
    target = str(context.get("target_id", ""))
    path = str(context.get("optimization_path", ""))
    if target == ORIN_TARGET and path == TRT_FULL_PIPELINE:
        return GuardDecision(
            blocked=True,
            reason=(
                "Jetson Orin TRT 10.3 does not support the backbone engine; "
                "trt_full_pipeline is blocked — use DiT-only (--inference-mode tensorrt)"
            ),
        )
    return GuardDecision(blocked=False, reason="")


def sync_over_inference_ceiling(context: dict[str, Any]) -> GuardDecision:
    """FR-INF-034 — block sync inference when `fps` exceeds the hw/policy ceiling.

    Args:
        context: `{target_id, policy_family, fps, mode}`.

    Returns:
        (GuardDecision) Blocked when mode is sync and fps is above the measured
            ceiling for the pair; allowed otherwise (including when no ceiling is
            known for the pair — an unmeasured pair is not silently blocked).
    """
    if str(context.get("mode", "")) != SYNC_MODE:
        return GuardDecision(blocked=False, reason="")
    target = str(context.get("target_id", ""))
    policy = str(context.get("policy_family", ""))
    ceiling = INFERENCE_CEILING_HZ.get((target, policy))
    if ceiling is None:
        return GuardDecision(blocked=False, reason="")
    fps = float(context.get("fps", 0.0))
    if fps > ceiling:
        return GuardDecision(
            blocked=True,
            reason=(
                f"fps={fps} exceeds the {ceiling} Hz sync ceiling for "
                f"{target}+{policy}; require RTC or async chunking"
            ),
        )
    return GuardDecision(blocked=False, reason="")
