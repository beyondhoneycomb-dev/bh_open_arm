// The forced re-zero flow for an unavoidable hardware relink (CG-G-S02c,
// FR-GUI-084). A hardware swap or CAN recovery is the ONE case where the backend
// must re-open the link, and that re-open runs the auto-zero path, which fixes the
// current physical pose as the new zero with NO error (02 §2.0.1 F-3'). Because the
// destruction is silent, the screen forces FOUR steps in order, none skippable:
//
//   1. rest-pose 3D confirm  — the operator confirms via the 3D viewport + joint
//      angles that the arm is at the URDF rest pose
//   2. new-zero warning       — the operator acknowledges the current pose becomes
//      the new zero
//   3. double confirm         — two independent confirmations
//   4. audit log              — a reason is recorded; the flow yields an audit entry
//
// This module is the gate only. It does not itself re-open the link and does not
// zero — it produces the operator's acknowledgements and the audit record the
// backend consumes. It calls no backend Robot method (I-2).

export const REZERO_STEP_IDS = [
  "rest_pose_confirm",
  "new_zero_warning",
  "double_confirm",
  "audit_log",
] as const;
export type RezeroStepId = (typeof REZERO_STEP_IDS)[number];

export const REZERO_STEP_LABELS: Record<RezeroStepId, string> = {
  rest_pose_confirm: "1. rest 자세 3D 확인",
  new_zero_warning: "2. 새 영점 경고 확인",
  double_confirm: "3. 이중 확인",
  audit_log: "4. 감사 로그",
};

// Two independent confirmations gate step 3.
export const DOUBLE_CONFIRM_COUNT = 2;

export interface RezeroState {
  // Steps completed, in order. Length is the current position in the flow.
  readonly completed: readonly RezeroStepId[];
  // Independent confirmations gathered for the double-confirm step.
  readonly confirmCount: number;
  // The recorded reason, empty until the audit step.
  readonly reason: string;
}

export const INITIAL_REZERO_STATE: RezeroState = {
  completed: [],
  confirmCount: 0,
  reason: "",
};

// The step the operator is currently on (the first not-yet-completed step), or
// null once all four are done.
export function currentRezeroStep(state: RezeroState): RezeroStepId | null {
  return REZERO_STEP_IDS[state.completed.length] ?? null;
}

// Whether a specific step is the current one — the only step that may advance. A
// caller cannot mark step 3 done while step 1 is pending, so the order holds.
export function isCurrentStep(state: RezeroState, step: RezeroStepId): boolean {
  return currentRezeroStep(state) === step;
}

// Acknowledge the rest-pose confirm (step 1). Advances only when it is current.
export function confirmRestPose(state: RezeroState): RezeroState {
  if (!isCurrentStep(state, "rest_pose_confirm")) {
    return state;
  }
  return { ...state, completed: [...state.completed, "rest_pose_confirm"] };
}

// Acknowledge the new-zero warning (step 2). Advances only when it is current.
export function acknowledgeNewZeroWarning(state: RezeroState): RezeroState {
  if (!isCurrentStep(state, "new_zero_warning")) {
    return state;
  }
  return { ...state, completed: [...state.completed, "new_zero_warning"] };
}

// Add one independent confirmation toward the double-confirm (step 3). The step
// completes only when DOUBLE_CONFIRM_COUNT confirmations have been gathered.
export function addConfirmation(state: RezeroState): RezeroState {
  if (!isCurrentStep(state, "double_confirm")) {
    return state;
  }
  const confirmCount = Math.min(state.confirmCount + 1, DOUBLE_CONFIRM_COUNT);
  if (confirmCount < DOUBLE_CONFIRM_COUNT) {
    return { ...state, confirmCount };
  }
  return { ...state, confirmCount, completed: [...state.completed, "double_confirm"] };
}

// Record the audit reason (step 4). A blank reason does not complete the flow —
// the audit log is not optional.
export function recordAudit(state: RezeroState, reason: string): RezeroState {
  if (!isCurrentStep(state, "audit_log")) {
    return state;
  }
  const trimmed = reason.trim();
  if (trimmed.length === 0) {
    return { ...state, reason: "" };
  }
  return { ...state, reason: trimmed, completed: [...state.completed, "audit_log"] };
}

// Whether all four steps are complete AND an audit reason is recorded. Only then
// may the re-zero proceed.
export function rezeroComplete(state: RezeroState): boolean {
  return (
    state.completed.length === REZERO_STEP_IDS.length && state.reason.trim().length > 0
  );
}

// The audit record the completed flow yields, or null if it is not complete. The
// backend persists it; the screen only produces it (FR-GUI-084 ④).
export interface RezeroAuditEntry {
  action: "hardware_swap_rezero";
  reason: string;
  side: string;
  monoMs: number;
}

export function rezeroAuditEntry(
  state: RezeroState,
  side: string,
  monoMs: number,
): RezeroAuditEntry | null {
  if (!rezeroComplete(state)) {
    return null;
  }
  return { action: "hardware_swap_rezero", reason: state.reason, side, monoMs };
}
