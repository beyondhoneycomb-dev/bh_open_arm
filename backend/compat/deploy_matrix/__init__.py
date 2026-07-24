"""Deployment-target inference-path block matrix (WP-4B-04, `02c` §2.4).

The enforceable form of the SPINE §7 deployment table: a target recognizer, the
per-(target, policy, fps) block matrix, the TensorRT promotion accuracy gate, and the
fp16-not-default-exposed static check. The per-target IK/inference bench harness lives in
`bench_runner`, imported directly because it pulls the sim/robot stack; it is not
re-exported here so the matrix engine stays importable without that stack.

The `11` §2.6 expected inference frequency is always LOOKED UP, never estimated
(`FR-INF-034`/`FR-TRN-004`), and a target-gate failure marks THAT target unsupported,
never a global failure (`02c` §2.4 음성 분기).
"""

from __future__ import annotations

from backend.compat.deploy_matrix.block_matrix import (
    DEFAULT_FPS,
    BlockReason,
    IkGateStatus,
    Optimization,
    TargetPolicyVerdict,
    evaluate,
    evaluate_fleet,
    policy_axis,
)
from backend.compat.deploy_matrix.expected_hz import (
    GROOT_2_6_TABLE,
    ExpectedHz,
    Groot26Row,
    estimate_violations,
    expected_hz,
    sourced_hz_values,
)
from backend.compat.deploy_matrix.fp16_staticcheck import (
    Fp16Violation,
    find_fp16_default_exposure,
    scan_source,
)
from backend.compat.deploy_matrix.target import (
    DeploymentTarget,
    TargetClass,
    UnsupportedTargetError,
    crosscheck_fleet_matrix,
    recognize_target,
    target_class,
)
from backend.compat.deploy_matrix.trt_promotion import (
    COSINE_PROMOTION_THRESHOLD,
    TrtPromotionVerdict,
    trt_promotion_verdict,
)

__all__ = [
    "COSINE_PROMOTION_THRESHOLD",
    "DEFAULT_FPS",
    "GROOT_2_6_TABLE",
    "BlockReason",
    "DeploymentTarget",
    "ExpectedHz",
    "Fp16Violation",
    "Groot26Row",
    "IkGateStatus",
    "Optimization",
    "TargetClass",
    "TargetPolicyVerdict",
    "TrtPromotionVerdict",
    "UnsupportedTargetError",
    "crosscheck_fleet_matrix",
    "estimate_violations",
    "evaluate",
    "evaluate_fleet",
    "expected_hz",
    "find_fp16_default_exposure",
    "policy_axis",
    "recognize_target",
    "scan_source",
    "sourced_hz_values",
    "target_class",
    "trt_promotion_verdict",
]
