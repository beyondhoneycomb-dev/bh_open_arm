// Calibration view — RENDER ONLY (WP-G-S02 contract, CTR-CAL@v1). It displays the
// persisted calibration record's fields and nothing more: the zero method, gripper
// open/close (radians), captured flag, timestamps, and offset/raw counts. It
// computes no value and edits nothing — the calibration canon is the backend's
// (WP-1-02). Angles are radians; no deg<->rad conversion.

import { JOINT_ANGLE_UNIT } from "./constants";
import { ZERO_METHOD_LABELS, type CalibrationRecord } from "./calibration";

interface CalibrationViewProps {
  calibration: CalibrationRecord | null;
}

function radLabel(value: number): string {
  return Number.isFinite(value) ? `${value.toFixed(4)} ${JOINT_ANGLE_UNIT}` : "—";
}

export function CalibrationView({ calibration }: CalibrationViewProps) {
  return (
    <section
      className="oa-s02-cal"
      aria-labelledby="oa-s02-cal-title"
      data-panel="calibration"
    >
      <h2 id="oa-s02-cal-title" className="oa-s02__panel-title">
        캘리브레이션 (CTR-CAL@v1 · 렌더 전용)
      </h2>

      {calibration === null ? (
        <p role="status" data-calibration="none">
          캘리브레이션 미캡처 — 명시적 set_zero 플로우로 영점을 확립하세요.
        </p>
      ) : (
        <dl className="oa-s02-cal__fields">
          <div>
            <dt>zero_method</dt>
            <dd data-field="zero-method">{ZERO_METHOD_LABELS[calibration.zeroMethod]}</dd>
          </div>
          <div>
            <dt>captured</dt>
            <dd data-field="captured">{calibration.captured ? "예" : "아니오"}</dd>
          </div>
          <div>
            <dt>gripper open</dt>
            <dd data-field="gripper-open">{radLabel(calibration.gripperOpenRad)}</dd>
          </div>
          <div>
            <dt>gripper close</dt>
            <dd data-field="gripper-close">{radLabel(calibration.gripperCloseRad)}</dd>
          </div>
          <div>
            <dt>captured_at</dt>
            <dd data-field="captured-at">{calibration.capturedAt ?? "—"}</dd>
          </div>
          <div>
            <dt>updated_at</dt>
            <dd data-field="updated-at">{calibration.updatedAt ?? "—"}</dd>
          </div>
          <div>
            <dt>urdf_zero_offset</dt>
            <dd data-field="urdf-zero-offset">
              {`${Object.keys(calibration.urdfZeroOffsetRad).length} 관절`}
            </dd>
          </div>
          <div>
            <dt>motor_zero_raw</dt>
            <dd data-field="motor-zero-raw">
              {`${Object.keys(calibration.motorZeroRaw).length} 모터`}
            </dd>
          </div>
        </dl>
      )}
    </section>
  );
}
