"""The deployment-target inference-path block matrix engine (`02c` §2.4, WP-4B-04).

This is the enforceable form of the SPINE §7 / `02c` §6.1 deployment table: given a
(target, policy, fps) triple, it renders a `TargetPolicyVerdict` naming which inference
backends and which optimization paths are blocked, with the source of each block. Its
job is to BLOCK — a missing block is the failure mode (an edge target silently running
30 Hz sync inference on a 4.6 Hz ceiling), not a missing pass.

Three facts drive every block, and all three are looked up rather than computed:

  * FR-INF-034 — sync is blocked when `fps` exceeds the pair's `11` §2.6 expected
    frequency (Jetson Orin + GR00T = 4.6 Hz). When the ceiling is unknown (no §2.6 row),
    the two target classes diverge (`02c` §6.1): a Jetson-class edge target blocks sync
    conservatively, an RTX-class workstation leaves it to its own self-bench.
  * FR-INF-033 — `trt_full_pipeline` is blocked on Jetson Orin (TRT 10.3 cannot compile
    the backbone engine; only DiT-only is allowed). Jetson Nano blocks it conservatively
    too until its TRT capability is self-confirmed (`02c` §6.1).
  * PG-IK-001 — the per-target IK gate. Its verdict needs the target's own hardware, so
    on this AI-offline band it is `DEFERRED`; the bench harness produces the input, the
    gate owns the number.

A target-gate failure marks THAT target unsupported, not a global failure (`02c` §2.4
음성 분기) — the verdict is per (target, policy), so one blocked cell never blocks another.

The backend vocabulary (`InferenceBackend`) is consumed from WP-4A-07 and the policy axis
(`POLICY_FAMILIES`) from WP-4B-01; neither is restated here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, StrEnum

from backend.compat.deploy_matrix.expected_hz import ExpectedHz, expected_hz
from backend.compat.deploy_matrix.target import (
    DeploymentTarget,
    TargetClass,
    target_class,
)
from backend.compat.policy_matrix.capability import POLICY_FAMILIES
from backend.inference.adapter.backend_kind import InferenceBackend

# The `11` §2.7 default control rate. A verdict is rendered against a specific fps; 30 is
# the value the sync ceiling is checked against unless a caller overrides it.
DEFAULT_FPS = 30.0


class Optimization(StrEnum):
    """The optimization paths a target may allow or block (`FR-INF-033`).

    `TRT_FULL_PIPELINE` is the full TensorRT path (backbone + action head); `TRT_DIT_ONLY`
    is the DiT-only path Orin is restricted to (`--inference-mode tensorrt`); `PYTORCH`
    is the unoptimised eager path. Only `TRT_FULL_PIPELINE` is ever blocked by this
    matrix — the point of the DiT-only allowance is that Orin is a `sync`-restricted
    target, not an unsupported one.
    """

    TRT_FULL_PIPELINE = "trt_full_pipeline"
    TRT_DIT_ONLY = "tensorrt"
    PYTORCH = "pytorch"


class IkGateStatus(Enum):
    """The per-target `PG-IK-001` status carried in a verdict (`03` §5.11).

    `DEFERRED` is this band's honest default: the IK p50/p99, unconstrained-fallback
    count and collision latency must be measured on the target's own hardware, which is
    absent here (AI-offline). The safety branch is the one exception the bench can decide
    without the target — a fallback firing is `FAIL_BLOCKING` regardless of host, because
    a limit-violating solution is a safety defect, not a performance one.
    """

    DEFERRED = "deferred"
    PASS = "pass"
    RETRY_WITH_VARIANT = "retry_with_variant"
    DEGRADED_ACCEPTED = "degraded_accepted"
    FAIL_BLOCKING = "fail_blocking"
    SUPERSEDED = "superseded"


@dataclass(frozen=True)
class BlockReason:
    """One reason a backend or optimization path is blocked, with its provenance.

    Attributes:
        code: The requirement or decision the block enforces (e.g. `FR-INF-034`).
        subject: What is blocked, as its enum value (e.g. `sync`, `trt_full_pipeline`).
        rationale: The operator-facing sentence naming the cause.
        source: Where the block comes from — a spec requirement or the `02c` §6.1 table.
    """

    code: str
    subject: str
    rationale: str
    source: str


@dataclass(frozen=True)
class TargetPolicyVerdict:
    """The block verdict for one (target, policy, fps) cell (`02c` §2.4 contract).

    Attributes:
        target: The deployment target.
        policy: The policy family.
        fps: The control rate the sync ceiling was checked against.
        expected_hz: The `11` §2.6 expected inference frequency, or None when unknown.
        expected_hz_source: The provenance of `expected_hz` (`FR-TRN-004`).
        blocked_backends: The inference backends this cell blocks (`SYNC` when the fps
            ceiling is exceeded or conservatively enforced); empty when none.
        blocked_optimizations: The optimization paths this cell blocks
            (`TRT_FULL_PIPELINE` on Jetson); empty when none.
        ik_gate: The `PG-IK-001` status — `DEFERRED` here (per-target hardware absent).
        required_alternatives: The backends offered in place of a blocked one — RTC or
            async chunking when sync is blocked (`FR-INF-034`); empty when sync is free.
        reasons: Every block reason that applies, with source; empty for an open cell.
    """

    target: DeploymentTarget
    policy: str
    fps: float
    expected_hz: float | None
    expected_hz_source: str
    blocked_backends: tuple[InferenceBackend, ...]
    blocked_optimizations: tuple[Optimization, ...]
    ik_gate: IkGateStatus
    required_alternatives: tuple[InferenceBackend, ...]
    reasons: tuple[BlockReason, ...]


# The non-sync backends offered when sync is blocked: RTC (real-time chunking) or the
# remote/async-chunking path (`FR-INF-034` requires "RTC or async chunking"). Derived
# from the WP-4A-07 enum so it moves with the backend set rather than being restated.
_ASYNC_ALTERNATIVES: tuple[InferenceBackend, ...] = tuple(
    backend for backend in InferenceBackend if backend is not InferenceBackend.SYNC
)


def _sync_block(target: DeploymentTarget, fps: float, ceiling: ExpectedHz) -> BlockReason | None:
    """Decide whether sync inference is blocked for a cell (`FR-INF-034`, `02c` §6.1).

    Args:
        target: The deployment target.
        fps: The configured control rate.
        ceiling: The looked-up expected frequency for the (target, policy) pair.

    Returns:
        (BlockReason | None) The block reason, or None when sync is permitted.
    """
    if ceiling.hz is not None:
        if fps > ceiling.hz:
            return BlockReason(
                code="FR-INF-034",
                subject=InferenceBackend.SYNC.value,
                rationale=(
                    f"fps={fps} exceeds the {ceiling.hz} Hz sync ceiling; require RTC or "
                    "async chunking"
                ),
                source=ceiling.source,
            )
        return None
    if target_class(target) is TargetClass.JETSON:
        return BlockReason(
            code="FR-INF-034/FR-TRN-004",
            subject=InferenceBackend.SYNC.value,
            rationale=(
                "expected inference frequency is unknown (no 11 §2.6 row) and estimation "
                "is forbidden; sync is blocked conservatively on this edge target until a "
                "self-bench establishes the ceiling"
            ),
            source="02c §6.1 (Jetson edge conservative default)",
        )
    return None


def _trt_full_block(target: DeploymentTarget) -> BlockReason | None:
    """Decide whether the full TensorRT pipeline is blocked (`FR-INF-033`, `02c` §6.1).

    Args:
        target: The deployment target.

    Returns:
        (BlockReason | None) The block reason, or None when the full pipeline is allowed.
    """
    if target is DeploymentTarget.JETSON_ORIN:
        return BlockReason(
            code="FR-INF-033",
            subject=Optimization.TRT_FULL_PIPELINE.value,
            rationale=(
                "TRT 10.3 cannot compile the backbone engine; trt_full_pipeline is "
                "blocked — only DiT-only (--inference-mode tensorrt) is allowed"
            ),
            source="11 §2.6 (Isaac-GR00T deployment README, Orin DiT-only)",
        )
    if target is DeploymentTarget.JETSON_NANO:
        return BlockReason(
            code="FR-INF-033/FR-TRN-004",
            subject=Optimization.TRT_FULL_PIPELINE.value,
            rationale=(
                "TRT capability is unconfirmed on this target; trt_full_pipeline is "
                "blocked conservatively until self-confirmed"
            ),
            source="02c §6.1 (Jetson Nano conservative default)",
        )
    return None


def evaluate(
    target: DeploymentTarget, policy: str, fps: float = DEFAULT_FPS
) -> TargetPolicyVerdict:
    """Render the block verdict for one (target, policy, fps) cell.

    Args:
        target: The deployment target.
        policy: The policy family, e.g. `groot`.
        fps: The control rate the sync ceiling is checked against (default 30).

    Returns:
        (TargetPolicyVerdict) The verdict naming blocked backends/optimizations, the
            sourced expected frequency, and the (deferred) IK gate status.
    """
    ceiling = expected_hz(target, policy)
    sync_reason = _sync_block(target, fps, ceiling)
    trt_reason = _trt_full_block(target)

    reasons = tuple(reason for reason in (sync_reason, trt_reason) if reason is not None)
    blocked_backends = (InferenceBackend.SYNC,) if sync_reason is not None else ()
    blocked_optimizations = (Optimization.TRT_FULL_PIPELINE,) if trt_reason is not None else ()
    required_alternatives = _ASYNC_ALTERNATIVES if sync_reason is not None else ()

    return TargetPolicyVerdict(
        target=target,
        policy=policy,
        fps=fps,
        expected_hz=ceiling.hz,
        expected_hz_source=ceiling.source,
        blocked_backends=blocked_backends,
        blocked_optimizations=blocked_optimizations,
        ik_gate=IkGateStatus.DEFERRED,
        required_alternatives=required_alternatives,
        reasons=reasons,
    )


def policy_axis() -> tuple[str, ...]:
    """Return the policy families the matrix crosses, from WP-4B-01's registry.

    Returns:
        (tuple[str, ...]) The `POLICY_FAMILIES` scope, consumed rather than restated.
    """
    return POLICY_FAMILIES


def evaluate_fleet(
    fps: float = DEFAULT_FPS, policies: tuple[str, ...] | None = None
) -> tuple[TargetPolicyVerdict, ...]:
    """Render every (target, policy) verdict across the fleet at one fps.

    Args:
        fps: The control rate to evaluate against (default 30).
        policies: The policy axis; defaults to WP-4B-01's `POLICY_FAMILIES`.

    Returns:
        (tuple[TargetPolicyVerdict, ...]) One verdict per (target, policy), target-major.
    """
    axis = policies if policies is not None else POLICY_FAMILIES
    return tuple(evaluate(target, policy, fps) for target in DeploymentTarget for policy in axis)
