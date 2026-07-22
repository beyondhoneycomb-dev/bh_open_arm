// The alignment state-machine view (CG-G-S05b, FR-GUI-107, FR-TEL-077/082). It
// renders the 11-state machine (`05` §4.1) with the backend's current state
// highlighted, the per-joint alignment error against the convergence band, and the
// follow-readiness gate: following cannot begin while alignment is incomplete, so
// the readiness indicator reads blocked until the backend reports `converged`.
//
// The only recovery affordance is re-engage, which requests a hold (S5/S6/S7) to
// leave back into ALIGNING (S3) — never straight into FOLLOWING. That routing is a
// `05` §4.2 invariant the backend enforces; the screen offers no path that skips it.

import {
  FORBIDDEN_TRANSITIONS,
  TELEOP_STATES,
  isFollowingState,
  isHoldState,
  stateById,
} from "./stateMachine";
import { canStartFollowing } from "./gates";
import type { TeleopSource } from "./teleopSource";

interface AlignmentStateMachineViewProps {
  source: TeleopSource;
  onReEngage: () => void;
}

export function AlignmentStateMachineView({ source, onReEngage }: AlignmentStateMachineViewProps) {
  const { alignment } = source;
  const current = stateById(alignment.currentState);
  const followReady = canStartFollowing(source);
  const following = isFollowingState(alignment.currentState);
  const inHold = isHoldState(alignment.currentState);

  return (
    <section className="oa-tel__align" aria-label="정렬 상태머신">
      <h2 className="oa-tel__h2">정렬 상태머신 ({TELEOP_STATES.length}상태)</h2>

      <p className="oa-tel__align-current" role="status" data-field="current-state">
        현재 상태: <strong>{current.id} · {current.name}</strong> ({current.label})
      </p>

      <p
        className="oa-tel__follow-gate"
        role="status"
        data-field="follow-readiness"
        data-blocked={followReady ? "false" : "true"}
      >
        {following
          ? "추종 중 (S4 FOLLOWING)"
          : followReady
            ? "추종 준비 완료 — 정렬 수렴, 클러치 체결 시 백엔드가 S4 진입"
            : "추종 불가 — 정렬 미완 (S3 ALIGNING 수렴 전에는 추종 시작 안 됨)"}
      </p>

      <div className="oa-tel__align-conv">
        <span>
          정렬 오차 max |q_target − q| = {alignment.maxErrorRad.toFixed(3)} rad
        </span>
        <span>
          수렴 임계 = {alignment.thresholdRad.toFixed(3)} rad ({alignment.converged ? "수렴" : "미수렴"})
        </span>
      </div>

      <ol className="oa-tel__joint-errors" aria-label="관절별 정렬 오차">
        {alignment.perJointErrorRad.map((error, index) => (
          <li key={source.jointNames[index] ?? index}>
            <span>{source.jointNames[index] ?? `j${index + 1}`}</span>
            <span data-field="joint-error">{error.toFixed(3)} rad</span>
            <span>{error < alignment.thresholdRad ? "✓" : "…"}</span>
          </li>
        ))}
      </ol>

      <ul className="oa-tel__states" aria-label="상태 목록">
        {TELEOP_STATES.map((state) => (
          <li
            key={state.id}
            className="oa-tel__state"
            data-current={state.id === current.id ? "true" : "false"}
            data-hold={state.isHold ? "true" : "false"}
          >
            <span className="oa-tel__state-id">{state.id}</span>
            <span className="oa-tel__state-name">{state.name}</span>
            <span className="oa-tel__state-out">{state.motorOutput}</span>
          </li>
        ))}
      </ul>

      <button
        type="button"
        className="oa-tel__reengage"
        data-field="re-engage"
        disabled={!inHold}
        onClick={onReEngage}
      >
        재-engage (홀드 → S3 정렬, 추종 직행 금지)
      </button>

      <details className="oa-tel__forbidden">
        <summary>금지 전이 (`05` §4.2 — 백엔드가 강제)</summary>
        <ul>
          {FORBIDDEN_TRANSITIONS.map((transition) => (
            <li key={`${transition.from}->${transition.to}`}>
              <code>{transition.from} → {transition.to}</code>: {transition.reason}
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}
