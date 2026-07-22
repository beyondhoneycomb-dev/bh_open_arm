// Elbow (nullspace swivel) slider (WP-G-S04, FR-MAN-024). The 7-DoF redundancy
// lets the elbow move while the end-effector pose is held. The slider is a
// normalized swivel intent (-1..1); the backend maps it to the posture/nullspace
// task. Crucially the emitted intent HOLDS the EE (eeHold, zero XYZ/RPY delta), so
// operating the slider moves the elbow and the EE stays put — 0 EE movement in the
// 3D (CG-G-S04i), which the reused viewport renders from backend FK.
//
// Emission is gated by the screen (arm+lease+freshness): dragging the slider while
// unarmed stages the value but sends nothing (CG-G-S04b). The screen's onCommand
// no-ops until armed.

import type { ManualCommand } from "./commands";
import type { ArmSide } from "./manualSource";

export interface ElbowSliderProps {
  side: ArmSide;
  value: number;
  onValueChange: (value: number) => void;
  onCommand: (command: ManualCommand) => void;
}

export function ElbowSlider({ side, value, onValueChange, onCommand }: ElbowSliderProps) {
  function handleChange(next: number): void {
    onValueChange(next);
    onCommand({
      op: "jog_nullspace",
      side,
      elbowDelta: next,
      eeHold: true,
      eeDeltaXyzMm: [0, 0, 0],
      eeDeltaRpyDeg: [0, 0, 0],
    });
  }

  return (
    <section className="oa-man-elbow" aria-labelledby="oa-man-elbow-title">
      <h2 id="oa-man-elbow-title">엘보 스위블 (널스페이스) — {side} 팔</h2>
      <p className="oa-man-elbow__note" role="note">
        EE 포즈 고정 — 엘보만 이동 (EE 이동 0)
      </p>
      <label className="oa-man-elbow__control">
        스위블: {value.toFixed(2)}
        <input
          type="range"
          min={-1}
          max={1}
          step={0.01}
          value={value}
          aria-label="엘보 스위블"
          data-field="elbow-swivel"
          onChange={(event) => handleChange(Number(event.target.value))}
        />
      </label>
    </section>
  );
}
