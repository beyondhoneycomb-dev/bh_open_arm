// The frozen bringup order (CG-G-S02b, 02 §2.0.4, FR-CON-062/063, 12 FR-SAF-075):
//
//   connect_readonly (torque-OFF backdrive) -> verify direction/zero by hand ->
//   explicit set_zero -> enable torque
//
// The order is an invariant with NO SKIP PATH. This module is that invariant made
// executable: it exposes only step-by-step advancement, so nothing can reach
// set_zero or enable without first passing connect_readonly and the hand-verify.
// The FIRST backend call the sequence emits is connect_readonly — that is the
// property CG-G-S02b checks, both statically (the ordered table below) and at
// runtime (the controller replays the same table).
//
// A step's `backendAction` is the WS command intent the screen dispatches when the
// operator advances into it; a `null` action is an operator-only step (moving the
// de-energised arm by hand is not a backend call). The screen SENDS this intent —
// it never calls the backend `Robot` itself, and there is no connect()/disconnect()
// anywhere in the path (I-2: connect() would destroy the zero).

export const BRINGUP_STEP_IDS = [
  "connect_readonly",
  "verify",
  "set_zero",
  "enable",
] as const;
export type BringupStepId = (typeof BRINGUP_STEP_IDS)[number];

// The backend command a step dispatches, or null for an operator-only step.
export type BringupBackendAction = "connect_readonly" | "set_zero" | "enable_torque";

export interface BringupStep {
  id: BringupStepId;
  label: string;
  detail: string;
  backendAction: BringupBackendAction | null;
  // Torque state the arm is in once this step completes (02 §2.0.4): OFF through
  // set_zero, ON only after the explicit enable. Rendered, never enforced here.
  torque: "off" | "on";
}

// The one ordered table. Its first row is connect_readonly by construction; the
// static half of CG-G-S02b reads exactly this ordering.
export const BRINGUP_STEPS: readonly BringupStep[] = [
  {
    id: "connect_readonly",
    label: "connect_readonly()",
    detail: "버스 오픈 + 모터 등록 + 피드백 워밍업 (torque OFF, set_zero 없음)",
    backendAction: "connect_readonly",
    torque: "off",
  },
  {
    id: "verify",
    label: "손 검증 (방향·영점)",
    detail: "무전원 상태로 손으로 팔을 움직여 방향과 영점을 확인",
    backendAction: null,
    torque: "off",
  },
  {
    id: "set_zero",
    label: "명시적 set_zero",
    detail: "전 모터 disable → settle → 모터별 0xFE → readback 검증 → 디스크 저장",
    backendAction: "set_zero",
    torque: "off",
  },
  {
    id: "enable",
    label: "Enable Torque",
    detail: "operator가 명시적으로 토크를 인가",
    backendAction: "enable_torque",
    torque: "on",
  },
];

export function bringupStep(id: BringupStepId): BringupStep {
  const found = BRINGUP_STEPS.find((step) => step.id === id);
  if (!found) {
    throw new Error(`unknown bringup step: ${id}`);
  }
  return found;
}

// The first backend action the sequence emits, in order. CG-G-S02b (static): this
// must be connect_readonly — the bringup never energises or zeroes before it.
export function firstBackendAction(): BringupBackendAction {
  const first = BRINGUP_STEPS.find((step) => step.backendAction !== null);
  if (!first || first.backendAction === null) {
    throw new Error("bringup declares no backend action");
  }
  return first.backendAction;
}

// The immediate successor of a step, or null at the end. The ONLY forward move —
// there is deliberately no jump-to-step function, so the order cannot be skipped.
export function nextBringupStepId(current: BringupStepId): BringupStepId | null {
  const index = BRINGUP_STEP_IDS.indexOf(current);
  if (index < 0 || index + 1 >= BRINGUP_STEP_IDS.length) {
    return null;
  }
  return BRINGUP_STEP_IDS[index + 1];
}

// A running bringup: how many steps have completed, and the ordered list of
// backend actions emitted so far. `completedCount === 0` is the pre-start state.
export interface BringupProgress {
  readonly completedCount: number;
  readonly emittedActions: readonly BringupBackendAction[];
}

export const INITIAL_BRINGUP_PROGRESS: BringupProgress = {
  completedCount: 0,
  emittedActions: [],
};

// Advance one step. Returns the next progress and the backend action emitted (null
// for an operator-only step). At the end it is a no-op. Advancement is strictly
// sequential: the step completed is always the immediate next one, so a runtime
// replay emits connect_readonly first (CG-G-S02b runtime).
export interface BringupAdvance {
  readonly progress: BringupProgress;
  readonly emitted: BringupBackendAction | null;
  readonly completedStep: BringupStepId | null;
}

export function advanceBringup(progress: BringupProgress): BringupAdvance {
  if (progress.completedCount >= BRINGUP_STEPS.length) {
    return { progress, emitted: null, completedStep: null };
  }
  const step = BRINGUP_STEPS[progress.completedCount];
  const emittedActions = step.backendAction
    ? [...progress.emittedActions, step.backendAction]
    : progress.emittedActions;
  return {
    progress: { completedCount: progress.completedCount + 1, emittedActions },
    emitted: step.backendAction,
    completedStep: step.id,
  };
}

export function bringupComplete(progress: BringupProgress): boolean {
  return progress.completedCount >= BRINGUP_STEPS.length;
}

// The step the operator would act on next, or null when bringup is complete.
export function pendingBringupStep(progress: BringupProgress): BringupStep | null {
  if (bringupComplete(progress)) {
    return null;
  }
  return BRINGUP_STEPS[progress.completedCount];
}
