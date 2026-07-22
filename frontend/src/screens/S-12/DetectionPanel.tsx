// Detection status and its enable path. The enable control is rendered ONLY when
// the backend gate permits it (evaluateDetectionGate). While the gate is unmet —
// PG-FRIC-001 not passed, or torque observation off — there is no enable control
// in the tree at all, and a standing banner states why (CG-G-S12b, FR-SAF-030).
// The screen never enables detection on its own: the button emits an intent the
// backend enforces.

import type { DetectionGateState } from "./detectionGate";
import type { DetectionStatus } from "./source";

interface DetectionPanelProps {
  status: DetectionStatus;
  gate: DetectionGateState;
  onEnableDetection: () => void;
}

const STATUS_LABELS: Readonly<Record<DetectionStatus, string>> = {
  DISABLED: "비활성 (DISABLED)",
  ARMED: "무장 (ARMED)",
  LATCHED: "래치 (LATCHED)",
};

export function DetectionPanel({ status, gate, onEnableDetection }: DetectionPanelProps) {
  const effectiveStatus = gate.forcedStatus ?? status;

  return (
    <section className="oa-safety__panel" aria-labelledby="oa-safety-detection-title">
      <h2 id="oa-safety-detection-title" className="oa-safety__panel-title">
        충돌 감지
      </h2>

      {gate.bannerText && (
        <div className="oa-safety__banner" role="alert" data-standing-banner="detection">
          <strong>감지 비활성</strong>
          <span>{gate.bannerText}</span>
        </div>
      )}

      <p className="oa-safety__status-line" role="status">
        상태: <b>{STATUS_LABELS[effectiveStatus]}</b>
      </p>

      {gate.enableAllowed && (
        <button
          type="button"
          className="oa-safety__btn"
          data-action="enable-detection"
          onClick={onEnableDetection}
        >
          충돌 감지 활성화
        </button>
      )}
    </section>
  );
}
