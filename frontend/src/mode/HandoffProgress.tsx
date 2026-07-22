// The four-step hand-off progress view (FR-GUI-082, CG-G-04c). Each step shows its
// status and its fail point, so an operator sees both where a hand-off is and where
// it can stall. A standing line states that the CAN stream is held throughout — a
// hand-off moves authority under a running scheduler and never breaks the stream
// (I-3). The view renders `HandoffState`; it drives no transition itself.

import { failPointFor, type HandoffState, type HandoffStepStatus } from "./handoff";

export interface HandoffProgressProps {
  state: HandoffState;
}

const STATUS_LABELS: Readonly<Record<HandoffStepStatus, string>> = {
  pending: "대기",
  active: "진행 중",
  done: "완료",
  failed: "실패",
};

export function HandoffProgress({ state }: HandoffProgressProps) {
  return (
    <section className="oa-handoff" aria-label="권리 이양 4단계">
      <ol className="oa-handoff__steps">
        {state.steps.map((step) => (
          <li key={step.id} className="oa-handoff__step" data-status={step.status}>
            <span className="oa-handoff__label">{step.label}</span>
            <span className="oa-handoff__status">{STATUS_LABELS[step.status]}</span>
            <span className="oa-handoff__failpoint">
              실패 지점: {step.failure ?? failPointFor(step.id)}
            </span>
          </li>
        ))}
      </ol>
      <p className="oa-handoff__stream" role="note">
        CAN 스트림 유지: {state.holdEmission} — 어느 단계에서도 단절 없음
      </p>
    </section>
  );
}
