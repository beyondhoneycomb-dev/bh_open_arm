// The four-step control hand-off, modelled so its progress and per-step failure
// points can be shown (FR-GUI-082, CG-G-04c). A mode transition is the MOVEMENT of
// send_action authority under a still-running scheduler (backend
// actuation.ModeTransition: prepare the incoming producer, one atomic swap, join
// the outgoing one). The scheduler never stops: every tick in the swap window
// emits MODE_TRANSITION_HOLD, so the CAN stream is continuous — cutting it would
// drop the arm (I-3, FR-GUI-082). This module carries that invariant at the type
// level: `streamContinuous` is the literal `true` and a failed step falls back to
// STOP_HOLD, never to a stream stop.

// The one hold emission that brackets a healthy transition (backend
// EmissionLabel.MODE_TRANSITION_HOLD). A failed step degrades to the STOP_HOLD
// reaction, which is still a continuous position-hold send, not a torque cut.
export const TRANSITION_HOLD = "MODE_TRANSITION_HOLD";
export const STOP_HOLD = "STOP_HOLD";

export type HoldEmission = typeof TRANSITION_HOLD | typeof STOP_HOLD;

// The four steps, in the fixed order of FR-GUI-082: the current owner stops
// commanding, the scheduler holds, the new owner acquires the right, and the new
// owner's first command is validated by the gateway.
export type HandoffStepId =
  | "current_owner_halt"
  | "stop_hold"
  | "new_owner_acquire"
  | "first_command_verify";

export type HandoffStepStatus = "pending" | "active" | "done" | "failed";

export interface HandoffStep {
  id: HandoffStepId;
  label: string;
  status: HandoffStepStatus;
  // Set only when status === "failed": the fail point rendered for this step.
  // CG-G-04c requires each step to show WHERE it can fail, so the view can name
  // the exact stage that stalled a hand-off.
  failure: string | null;
}

interface StepSpec {
  id: HandoffStepId;
  label: string;
  // The fail point copy shown when this step fails.
  failPoint: string;
}

const STEP_SPECS: readonly StepSpec[] = [
  {
    id: "current_owner_halt",
    label: "① 현 소유자 명령 중단",
    failPoint: "현 소유자가 권리를 놓지 않음 (여전히 send_action 발행)",
  },
  {
    id: "stop_hold",
    label: "② STOP_HOLD 유지",
    failPoint: "홀드 프레임 미발행 — 스트림 공백 (낙하 위험)",
  },
  {
    id: "new_owner_acquire",
    label: "③ 신규 소유자 권리 획득",
    failPoint: "획득 거부 (lease anti-replay / 역할 불충분)",
  },
  {
    id: "first_command_verify",
    label: "④ 첫 명령 검증",
    failPoint: "첫 명령이 게이트웨이 검증 실패 (리밋/스키마)",
  },
];

export interface HandoffState {
  steps: readonly HandoffStep[];
  // Which hold the scheduler is emitting while the hand-off is in flight. A failed
  // step degrades TRANSITION_HOLD -> STOP_HOLD but never drops the stream.
  holdEmission: HoldEmission;
  // Structural invariant: the CAN stream is never broken across a hand-off
  // (FR-GUI-082, I-3). The literal `true` type makes a stream break unrepresentable.
  streamContinuous: true;
}

// The fail point copy for a step id, so the view can show every step's failure
// point even before any step has failed (CG-G-04c).
export function failPointFor(id: HandoffStepId): string {
  const spec = STEP_SPECS.find((candidate) => candidate.id === id);
  if (!spec) {
    throw new Error(`unknown hand-off step id: ${id}`);
  }
  return spec.failPoint;
}

// Begin a hand-off: step one active, the rest pending, held under
// MODE_TRANSITION_HOLD with a continuous stream.
export function beginHandoff(): HandoffState {
  const steps = STEP_SPECS.map((spec, index) => makeStep(spec, index === 0 ? "active" : "pending"));
  return { steps, holdEmission: TRANSITION_HOLD, streamContinuous: true };
}

// Mark the active step done and advance to the next; the last step completing
// leaves every step done. The stream stays continuous throughout.
export function completeCurrentStep(state: HandoffState): HandoffState {
  const activeIndex = state.steps.findIndex((step) => step.status === "active");
  if (activeIndex === -1) {
    return state;
  }
  const steps = state.steps.map((step, index) => {
    if (index === activeIndex) {
      return { ...step, status: "done" as HandoffStepStatus };
    }
    if (index === activeIndex + 1) {
      return { ...step, status: "active" as HandoffStepStatus };
    }
    return step;
  });
  return { ...state, steps };
}

// Fail the active step, recording its fail point. The scheduler drops to STOP_HOLD
// — still a continuous hold send, so `streamContinuous` stays true (a failed
// hand-off holds the arm, it never releases it).
export function failCurrentStep(state: HandoffState): HandoffState {
  const activeIndex = state.steps.findIndex((step) => step.status === "active");
  if (activeIndex === -1) {
    return state;
  }
  const steps = state.steps.map((step, index) =>
    index === activeIndex
      ? { ...step, status: "failed" as HandoffStepStatus, failure: failPointFor(step.id) }
      : step,
  );
  return { ...state, steps, holdEmission: STOP_HOLD, streamContinuous: true };
}

function makeStep(spec: StepSpec, status: HandoffStepStatus): HandoffStep {
  return { id: spec.id, label: spec.label, status, failure: null };
}
