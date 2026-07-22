// The bringup panel (CG-G-S02a/b/e). It drives the frozen bringup order through
// the bringup.ts state machine, which allows only single-step advancement — there
// is no control that skips ahead. The whole flow is gated two ways:
//
//   * side unchosen  -> progress impossible (CG-G-S02a): the advance control is
//     disabled and the reason is shown, because an unset side silently locks the
//     arm and the screen is the only defence.
//   * CAN-FD unverified -> startup blocked (CG-G-S02e): connect_readonly opens the
//     bus, which cannot happen until the CAN-FD `ip link` fact is verified.
//
// Advancing the first step emits the connect_readonly intent first (CG-G-S02b
// runtime). The panel SENDS intent via onAction and renders the emitted-action log;
// it never calls the backend Robot and holds no connect()/disconnect() path.

import { useState } from "react";

import { BRINGUP_READONLY_NOTICE } from "./constants";
import {
  advanceBringup,
  BRINGUP_STEPS,
  bringupComplete,
  INITIAL_BRINGUP_PROGRESS,
  pendingBringupStep,
  type BringupBackendAction,
  type BringupProgress,
} from "./bringup";
import { canProceedWithSide, type SideSelection } from "./sideSelection";

interface BringupPanelProps {
  side: SideSelection;
  // True when CAN-FD is unverified on any interface (startup blocked, CG-G-S02e).
  canStartupBlocked: boolean;
  // Receives each backend action the operator emits, in order. The screen wires
  // this to the WS command intent; tests capture the sequence.
  onAction?: (action: BringupBackendAction) => void;
}

export function BringupPanel({ side, canStartupBlocked, onAction }: BringupPanelProps) {
  const [progress, setProgress] = useState<BringupProgress>(INITIAL_BRINGUP_PROGRESS);

  const sideChosen = canProceedWithSide(side);
  const gated = !sideChosen || canStartupBlocked;
  const pending = pendingBringupStep(progress);
  const done = bringupComplete(progress);

  function advance(): void {
    if (gated || done) {
      return;
    }
    const result = advanceBringup(progress);
    setProgress(result.progress);
    if (result.emitted) {
      onAction?.(result.emitted);
    }
  }

  return (
    <section
      className="oa-s02-bringup"
      aria-labelledby="oa-s02-bringup-title"
      data-panel="bringup"
    >
      <h2 id="oa-s02-bringup-title" className="oa-s02__panel-title">
        브링업 (connect_readonly → 검증 → set_zero → Enable)
      </h2>

      <p className="oa-s02-bringup__notice" role="note">
        {BRINGUP_READONLY_NOTICE}
      </p>

      <ol className="oa-s02-bringup__steps">
        {BRINGUP_STEPS.map((step, index) => {
          const status =
            index < progress.completedCount
              ? "done"
              : index === progress.completedCount
                ? "current"
                : "pending";
          return (
            <li key={step.id} data-step={step.id} data-step-status={status}>
              <span className="oa-s02-bringup__step-label">{step.label}</span>
              <span className="oa-s02-bringup__step-detail">{step.detail}</span>
              <span className="oa-s02-bringup__step-torque" data-torque={step.torque}>
                {`torque ${step.torque.toUpperCase()}`}
              </span>
            </li>
          );
        })}
      </ol>

      {gated && (
        <p className="oa-s02-bringup__gate" role="alert" data-gate="blocked">
          {!sideChosen
            ? "side 미선택 — 진행 불가"
            : "CAN-FD 미검증 — 기동 차단"}
        </p>
      )}

      <button
        type="button"
        className="oa-s02-bringup__advance"
        onClick={advance}
        disabled={gated || done}
        data-action="advance-bringup"
      >
        {done
          ? "브링업 완료"
          : pending
            ? `다음 단계: ${pending.label}`
            : "다음 단계"}
      </button>

      <ol className="oa-s02-bringup__log" aria-label="발행된 백엔드 명령" data-log="actions">
        {progress.emittedActions.map((action, index) => (
          <li key={`${action}-${index}`} data-emitted={action}>
            {action}
          </li>
        ))}
      </ol>
    </section>
  );
}
