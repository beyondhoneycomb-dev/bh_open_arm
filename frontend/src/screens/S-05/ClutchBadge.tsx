// The clutch (deadman) badge (CG-G-S05c, FR-TEL-030/031, FR-GUI-107). The clutch
// state is shown at all times, and the re-grip delta is shown as the backend
// reports it: releasing the clutch discards the pose reference and re-gripping
// re-captures it, so at the re-grip instant the delta is exactly zero and the
// follower does not jump. The screen renders the backend's `regripDelta*` — it
// measures no delta and decides no grip threshold.

import type { ClutchStatus } from "./teleopSource";

interface ClutchBadgeProps {
  clutch: ClutchStatus;
}

export function ClutchBadge({ clutch }: ClutchBadgeProps) {
  const stateLabel = clutch.engaged ? "체결 (ENGAGED)" : "해제 (RELEASED)";

  return (
    <section className="oa-tel__clutch" aria-label="클러치 상태">
      <h2 className="oa-tel__h2">클러치 (데드맨)</h2>
      <p
        className="oa-tel__clutch-state"
        role="status"
        data-field="clutch-state"
        data-engaged={clutch.engaged ? "true" : "false"}
      >
        상태: {stateLabel}
      </p>
      <dl className="oa-tel__kv">
        <div>
          <dt>grip 값</dt>
          <dd data-field="clutch-grip">{clutch.gripValue.toFixed(2)}</dd>
        </div>
        <div>
          <dt>기준점 래치</dt>
          <dd>{clutch.referenceLatched ? "래치됨" : "파기됨"}</dd>
        </div>
        <div>
          <dt>재파지 위치 델타</dt>
          <dd data-field="regrip-delta-pos">{clutch.regripDeltaPosMm.toFixed(1)} mm</dd>
        </div>
        <div>
          <dt>재파지 회전 델타</dt>
          <dd data-field="regrip-delta-rot">{clutch.regripDeltaRotDeg.toFixed(1)}°</dd>
        </div>
      </dl>
      <p className="oa-tel__hint">
        클러치 해제 → 기준점 파기 · 재파지 → 기준점 재캡처 → 델타 0에서 시작 (급발진 방지, `05` §4.2 #7)
      </p>
    </section>
  );
}
