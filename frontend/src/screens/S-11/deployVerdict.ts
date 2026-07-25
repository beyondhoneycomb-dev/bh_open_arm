// Projections of the WP-4B-04 deployment-target block-matrix verdict (CG-G-S11g/h,
// PG-IK-001). Every function here READS the committed `TargetPolicyVerdict` — which
// backends are blocked, which optimizations are blocked, which alternatives are required,
// and the per-target IK gate status — and never recomputes any of it. The matrix engine
// (block_matrix.py) owns the decision; this module only decides how to disable an option
// and what label to render, from the verdict the backend already produced.

import type {
  DeployBlockReason,
  InferenceBackend,
  Optimization,
  TargetPolicyVerdict,
} from "./types";
import { INFERENCE_BACKENDS, OPTIMIZATIONS } from "./types";

// Whether a backend is blocked for the active (target, policy, fps) cell (CG-G-S11g).
export function isBackendBlocked(
  verdict: TargetPolicyVerdict,
  backend: InferenceBackend,
): boolean {
  return verdict.blockedBackends.includes(backend);
}

// The reason a backend is blocked, found by subject in the verdict's reasons — the
// backend's own sentence with its source (FR-INF-034), never a UI-authored string. Null
// when the backend is not blocked.
export function backendBlockReason(
  verdict: TargetPolicyVerdict,
  backend: InferenceBackend,
): DeployBlockReason | null {
  if (!isBackendBlocked(verdict, backend)) {
    return null;
  }
  return verdict.reasons.find((reason) => reason.subject === backend) ?? null;
}

// The backends this cell leaves open, in the canonical order.
export function allowedBackends(verdict: TargetPolicyVerdict): InferenceBackend[] {
  return INFERENCE_BACKENDS.filter((backend) => !isBackendBlocked(verdict, backend));
}

// Whether an optimization path is blocked for the active cell (CG-G-S11h).
export function isOptimizationBlocked(
  verdict: TargetPolicyVerdict,
  optimization: Optimization,
): boolean {
  return verdict.blockedOptimizations.includes(optimization);
}

// The reason an optimization is blocked, found by subject (FR-INF-033). Null when open.
export function optimizationBlockReason(
  verdict: TargetPolicyVerdict,
  optimization: Optimization,
): DeployBlockReason | null {
  if (!isOptimizationBlocked(verdict, optimization)) {
    return null;
  }
  return verdict.reasons.find((reason) => reason.subject === optimization) ?? null;
}

// The optimization paths this cell leaves open.
export function allowedOptimizations(verdict: TargetPolicyVerdict): Optimization[] {
  return OPTIMIZATIONS.filter((optimization) => !isOptimizationBlocked(verdict, optimization));
}

// How a target's PG-IK-001 status renders (03 §5.11). A `fail_blocking` IK gate means the
// target is UNSUPPORTED — the screen renders that backend fact, it does not decide it
// (a limit-violating IK solution is a safety defect the bench declares). `deferred` is the
// honest AI-offline state (per-target hardware absent); `pass` is supported. The label is
// operator-facing text derived from the verdict, never a recomputation of the gate.
export interface TargetSupport {
  supported: boolean;
  label: string;
  note: string;
}

export function targetSupport(verdict: TargetPolicyVerdict): TargetSupport {
  switch (verdict.ikGate) {
    case "fail_blocking":
      return {
        supported: false,
        label: "미지원",
        note: "PG-IK-001 미달 — 리밋 위반 IK 해가 발생하는 타깃",
      };
    case "deferred":
      return {
        supported: false,
        label: "IK 게이트 보류",
        note: "PG-IK-001 실측 필요 (타깃 하드웨어 부재 — AI-offline)",
      };
    case "retry_with_variant":
      return { supported: false, label: "재시도 필요", note: "PG-IK-001 변형 재시도 대기" };
    case "degraded_accepted":
      return { supported: true, label: "축소 수용", note: "PG-IK-001 성능 저하 수용" };
    case "superseded":
      return { supported: false, label: "대체됨", note: "PG-IK-001 후속 측정으로 대체" };
    case "pass":
    default:
      return { supported: true, label: "지원", note: "PG-IK-001 통과" };
  }
}
