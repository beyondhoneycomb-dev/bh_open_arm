// The inference-control lock gate (CG-G-S11a / FR-INF-027). The SERVER is the schema
// authority: a schema or policy-feature version mismatch is rejected downstream as
// INVALID_ARGUMENT, so the screen must LOCK its control UI FIRST — before an operator can
// send a start/mode/task/takeover intent that the server would only reject. This module
// composes the server-reported negotiation into the lock; it renders the server's
// `status`, it does not decide the mismatch itself (the facade discipline). Every control
// affordance on the screen reads `isControlLocked` and disables on true, so there is no UI
// path to drive inference across a version skew.

import type { SchemaNegotiation } from "./types";

// The human-readable reasons the control UI is locked, in the order an operator reads
// them. Empty means the gate is clear. A MISMATCH always locks; each mismatched version
// axis is named so the operator sees exactly which version disagrees.
export function controlLockReasons(schema: SchemaNegotiation): string[] {
  if (schema.status !== "MISMATCH") {
    return [];
  }
  const reasons: string[] = [];
  if (schema.clientSchemaVersion !== schema.serverSchemaVersion) {
    reasons.push(
      `스키마 버전 불일치: 클라이언트 ${schema.clientSchemaVersion} / 서버 ${schema.serverSchemaVersion}`,
    );
  }
  if (schema.clientPolicyFeatureVersion !== schema.serverPolicyFeatureVersion) {
    reasons.push(
      `policy feature 버전 불일치: 클라이언트 ${schema.clientPolicyFeatureVersion} / ` +
        `서버 ${schema.serverPolicyFeatureVersion}`,
    );
  }
  // A MISMATCH with no axis difference still locks — the server declared it, and the
  // server is the authority. Fall back to its detail so the lock is never reasonless.
  if (reasons.length === 0) {
    reasons.push(schema.detail || "서버가 스키마 불일치를 보고함");
  }
  reasons.push("서버가 INVALID_ARGUMENT로 거부하므로 추론 제어가 잠깁니다");
  return reasons;
}

// Whether the inference-control UI is locked: locked exactly when a lock reason stands.
export function isControlLocked(schema: SchemaNegotiation): boolean {
  return controlLockReasons(schema).length > 0;
}
