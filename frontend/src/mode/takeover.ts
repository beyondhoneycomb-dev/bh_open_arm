// Force-takeover of the control lease: double-confirm + reason + audit, with
// torque held throughout (FR-GUI-085, FR-OPS-076/079/091, CG-G-04f). Force-release
// recovers a deadlocked lease, but it happens with the robot held in STOP_HOLD —
// releasing torque before recovery is a drop (no holding brake, I-5). This module
// validates the request and produces the audit record and the lease-generation
// bump; the recovery path has NO torque-release step, and the type system makes
// that non-negotiable (`torqueRetainedAsStopHold` is the literal `true`).

import type { LeaseRole } from "./roles";

// The audit record shape is FR-OPS-079's {t, user, role, action, target, before,
// after, reason}. Force-release is one of the audited actions; the browser fills
// the fields the operator supplies and the backend persists it to the session log.
export type AuditAction =
  | "control_acquire"
  | "control_release"
  | "force_takeover";

export interface AuditRecord {
  // Monotonic/epoch time the action was requested, supplied by the caller's clock.
  t: number;
  user: string;
  role: LeaseRole;
  action: AuditAction;
  // What the action acted on — here, the outgoing session losing control.
  target: string;
  before: string;
  after: string;
  reason: string;
}

// Why a force-takeover request was refused. Each maps to a required guard: an
// admin role (FR-OPS-078), a stated reason, and both confirmations (FR-GUI-085).
export type TakeoverError =
  | "admin_role_required"
  | "reason_required"
  | "double_confirm_required";

export interface ForceTakeoverRequest {
  user: string;
  role: LeaseRole;
  reason: string;
  // Two independent confirmations — a single confirm is not enough (FR-GUI-085).
  firstConfirm: boolean;
  secondConfirm: boolean;
  // The session being forced out and the session taking over.
  outgoingSession: string;
  incomingSession: string;
}

export interface ForceTakeoverPlan {
  audit: AuditRecord;
  // The lease generation the takeover moves to. Bumping it invalidates the old
  // holder's residual and replayed frames (FR-OPS-091), which is what closes the
  // window CG-G-04d's anti-replay guards.
  nextLeaseGeneration: number;
  // The takeover is performed with the robot held as STOP_HOLD; torque is never
  // released first (CG-G-04f). The literal `true` type means no code path can
  // produce a plan that releases torque.
  torqueRetainedAsStopHold: true;
}

export type ForceTakeoverResult =
  | { ok: true; plan: ForceTakeoverPlan }
  | { ok: false; errors: TakeoverError[] };

// Validate a force-takeover request and, when it passes, produce the audit record,
// the generation bump and the torque-retained plan. Every guard is checked so the
// dialog can show all missing requirements at once rather than one at a time.
export function planForceTakeover(
  request: ForceTakeoverRequest,
  currentGeneration: number,
  now: number,
): ForceTakeoverResult {
  const errors: TakeoverError[] = [];
  if (request.role !== "admin") {
    errors.push("admin_role_required");
  }
  if (request.reason.trim().length === 0) {
    errors.push("reason_required");
  }
  if (!request.firstConfirm || !request.secondConfirm) {
    errors.push("double_confirm_required");
  }
  if (errors.length > 0) {
    return { ok: false, errors };
  }

  const audit: AuditRecord = {
    t: now,
    user: request.user,
    role: request.role,
    action: "force_takeover",
    target: request.outgoingSession,
    before: `holder=${request.outgoingSession}`,
    after: `holder=${request.incomingSession}`,
    reason: request.reason.trim(),
  };
  return {
    ok: true,
    plan: {
      audit,
      nextLeaseGeneration: currentGeneration + 1,
      torqueRetainedAsStopHold: true,
    },
  };
}
