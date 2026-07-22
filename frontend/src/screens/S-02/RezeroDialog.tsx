// The forced re-zero dialog for an unavoidable hardware relink (CG-G-S02c,
// FR-GUI-084). It forces all four steps in order through rezeroFlow.ts, which
// advances only the current step — no step can be skipped, and completion needs an
// audit reason. Step 1 embeds the 3D rest-pose confirm (reusing the viewport via
// ZeroConfirmView); step 2 is the new-zero warning; step 3 needs two confirmations;
// step 4 records the audit. On completion the dialog yields the audit entry for the
// backend to persist — it performs no relink and no zeroing itself.

import { useState } from "react";

import { REZERO_NEW_ZERO_WARNING } from "./constants";
import {
  acknowledgeNewZeroWarning,
  addConfirmation,
  confirmRestPose,
  currentRezeroStep,
  DOUBLE_CONFIRM_COUNT,
  INITIAL_REZERO_STATE,
  rezeroAuditEntry,
  rezeroComplete,
  REZERO_STEP_IDS,
  REZERO_STEP_LABELS,
  recordAudit,
  type RezeroAuditEntry,
  type RezeroState,
} from "./rezeroFlow";
import { ZeroConfirmView } from "./ZeroConfirmView";

interface RezeroDialogProps {
  side: string;
  jointNames: readonly string[];
  restPositionsRad: Readonly<Record<string, number>>;
  currentPositionsRad: Readonly<Record<string, number>> | null;
  nowMonoMs: number;
  onComplete?: (entry: RezeroAuditEntry) => void;
}

export function RezeroDialog({
  side,
  jointNames,
  restPositionsRad,
  currentPositionsRad,
  nowMonoMs,
  onComplete,
}: RezeroDialogProps) {
  const [state, setState] = useState<RezeroState>(INITIAL_REZERO_STATE);
  const [reason, setReason] = useState<string>("");

  const current = currentRezeroStep(state);
  const complete = rezeroComplete(state);

  function apply(next: RezeroState): void {
    setState(next);
    if (rezeroComplete(next)) {
      const entry = rezeroAuditEntry(next, side, nowMonoMs);
      if (entry) {
        onComplete?.(entry);
      }
    }
  }

  function stepStatus(index: number): "done" | "current" | "pending" {
    if (index < state.completed.length) {
      return "done";
    }
    return index === state.completed.length ? "current" : "pending";
  }

  return (
    <section
      className="oa-s02-rezero"
      aria-labelledby="oa-s02-rezero-title"
      data-panel="rezero"
    >
      <h2 id="oa-s02-rezero-title" className="oa-s02__panel-title">
        재영점 (부득이한 하드웨어 교체·CAN 복구)
      </h2>

      <p className="oa-s02-rezero__warning" role="alert">
        {REZERO_NEW_ZERO_WARNING}
      </p>

      <ol className="oa-s02-rezero__steps">
        {REZERO_STEP_IDS.map((stepId, index) => (
          <li key={stepId} data-step={stepId} data-step-status={stepStatus(index)}>
            {REZERO_STEP_LABELS[stepId]}
          </li>
        ))}
      </ol>

      {current === "rest_pose_confirm" && (
        <div className="oa-s02-rezero__panel" data-active-step="rest_pose_confirm">
          <ZeroConfirmView
            jointNames={jointNames}
            restPositionsRad={restPositionsRad}
            currentPositionsRad={currentPositionsRad}
            nowMonoMs={nowMonoMs}
          />
          <button
            type="button"
            onClick={() => apply(confirmRestPose(state))}
            data-action="confirm-rest-pose"
          >
            현재 자세가 rest 자세임을 확인
          </button>
        </div>
      )}

      {current === "new_zero_warning" && (
        <div className="oa-s02-rezero__panel" data-active-step="new_zero_warning">
          <p role="alert">{REZERO_NEW_ZERO_WARNING}</p>
          <button
            type="button"
            onClick={() => apply(acknowledgeNewZeroWarning(state))}
            data-action="ack-new-zero"
          >
            현재 자세가 새 영점이 됨을 이해했습니다
          </button>
        </div>
      )}

      {current === "double_confirm" && (
        <div className="oa-s02-rezero__panel" data-active-step="double_confirm">
          <p role="status" data-confirm-count={state.confirmCount}>
            {`이중 확인: ${state.confirmCount}/${DOUBLE_CONFIRM_COUNT}`}
          </p>
          <button
            type="button"
            onClick={() => apply(addConfirmation(state))}
            data-action="add-confirmation"
          >
            확인 추가
          </button>
        </div>
      )}

      {current === "audit_log" && (
        <div className="oa-s02-rezero__panel" data-active-step="audit_log">
          <label className="oa-s02-rezero__reason">
            사유 (감사 로그)
            <input
              type="text"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              data-input="audit-reason"
            />
          </label>
          <button
            type="button"
            onClick={() => apply(recordAudit(state, reason))}
            disabled={reason.trim().length === 0}
            data-action="record-audit"
          >
            감사 로그 기록 후 재영점 승인
          </button>
        </div>
      )}

      {complete && (
        <p className="oa-s02-rezero__done" role="status" data-rezero="complete">
          {`재영점 4단계 완료 — 감사 사유: ${state.reason}`}
        </p>
      )}
    </section>
  );
}
