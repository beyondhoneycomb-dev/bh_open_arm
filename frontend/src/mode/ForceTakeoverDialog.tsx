// The force-takeover dialog (FR-GUI-085, CG-G-04f). Forcing a deadlocked lease
// requires a reason, two independent confirmations, and an admin role, and it
// produces an audit record. A standing warning states that torque is NOT released —
// the takeover runs with the robot held as STOP_HOLD, because releasing torque
// before recovery is a drop (no holding brake, I-5). The dialog collects input and
// calls onConfirm only with a validated plan; it never releases torque and never
// reconnects the link.

import { useState } from "react";

import { ROLE_LABELS, type LeaseRole } from "./roles";
import {
  planForceTakeover,
  type ForceTakeoverPlan,
  type TakeoverError,
} from "./takeover";

export interface ForceTakeoverDialogProps {
  role: LeaseRole;
  user: string;
  outgoingSession: string;
  incomingSession: string;
  currentGeneration: number;
  // Injectable clock so the audit timestamp is deterministic under test.
  now: () => number;
  onConfirm: (plan: ForceTakeoverPlan) => void;
  onCancel: () => void;
}

const ERROR_LABELS: Readonly<Record<TakeoverError, string>> = {
  admin_role_required: "관리자 권한이 필요합니다.",
  reason_required: "사유를 입력해야 합니다.",
  double_confirm_required: "두 번의 확인이 모두 필요합니다.",
};

export function ForceTakeoverDialog({
  role,
  user,
  outgoingSession,
  incomingSession,
  currentGeneration,
  now,
  onConfirm,
  onCancel,
}: ForceTakeoverDialogProps) {
  const [reason, setReason] = useState("");
  const [firstConfirm, setFirstConfirm] = useState(false);
  const [secondConfirm, setSecondConfirm] = useState(false);
  const [errors, setErrors] = useState<TakeoverError[]>([]);

  function submit() {
    const result = planForceTakeover(
      { user, role, reason, firstConfirm, secondConfirm, outgoingSession, incomingSession },
      currentGeneration,
      now(),
    );
    if (result.ok) {
      setErrors([]);
      onConfirm(result.plan);
    } else {
      setErrors(result.errors);
    }
  }

  return (
    <div className="oa-takeover" role="dialog" aria-modal="true" aria-label="제어권 강제 회수">
      <p className="oa-takeover__warning" role="alert">
        경고: 회수는 STOP_HOLD 유지 상태로 진행됩니다 — 토크를 해제하지 않습니다 (낙하 방지).
      </p>
      <p className="oa-takeover__role">
        요청자: {user} ({ROLE_LABELS[role]})
      </p>
      <label className="oa-takeover__reason">
        사유
        <textarea
          aria-label="회수 사유"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />
      </label>
      <label className="oa-takeover__confirm">
        <input
          type="checkbox"
          aria-label="1차 확인"
          checked={firstConfirm}
          onChange={(event) => setFirstConfirm(event.target.checked)}
        />
        1차 확인: 현 소유자 권리를 회수함
      </label>
      <label className="oa-takeover__confirm">
        <input
          type="checkbox"
          aria-label="2차 확인"
          checked={secondConfirm}
          onChange={(event) => setSecondConfirm(event.target.checked)}
        />
        2차 확인: STOP_HOLD 유지 상태에서 회수함
      </label>
      {errors.length > 0 ? (
        <ul className="oa-takeover__errors" role="alert">
          {errors.map((error) => (
            <li key={error}>{ERROR_LABELS[error]}</li>
          ))}
        </ul>
      ) : null}
      <div className="oa-takeover__actions">
        <button type="button" onClick={submit}>
          강제 회수
        </button>
        <button type="button" onClick={onCancel}>
          취소
        </button>
      </div>
    </div>
  );
}
