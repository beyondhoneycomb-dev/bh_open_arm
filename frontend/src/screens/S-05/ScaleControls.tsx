// The delta-mapping scale controls (CG-G-S05e, FR-TEL-029/033). Position scale and
// rotation scale are SEPARATE controls and never share a value: joint6's ±45° limit
// makes a 1:1 attitude mapping sit permanently at the limit, so the operator narrows
// rotation without shrinking translation. Each control ships its value to the backend,
// which owns the mapping and the adjustable range; the sliders present that range as
// a display affordance, not a self-clamp.

import { useState } from "react";

import type { ScaleStatus } from "./teleopSource";

interface ScaleControlsProps {
  scale: ScaleStatus;
  disabled: boolean;
  onPositionScale: (value: number) => void;
  onRotationScale: (value: number) => void;
}

export function ScaleControls({ scale, disabled, onPositionScale, onRotationScale }: ScaleControlsProps) {
  const [positionScale, setPositionScale] = useState(scale.positionScale);
  const [rotationScale, setRotationScale] = useState(scale.rotationScale);

  return (
    <section className="oa-tel__scale" aria-label="스케일 (위치·회전 분리)">
      <h2 className="oa-tel__h2">델타 스케일</h2>

      <div className="oa-tel__param" data-control="position-scale">
        <label htmlFor="oa-tel-position-scale">위치 스케일 (position_scale)</label>
        <input
          id="oa-tel-position-scale"
          type="range"
          data-field="position-scale"
          min={scale.positionScaleMin}
          max={scale.positionScaleMax}
          step={0.05}
          value={positionScale}
          disabled={disabled}
          onChange={(event) => {
            const next = Number(event.target.value);
            setPositionScale(next);
            onPositionScale(next);
          }}
        />
        <output data-field="position-scale-value">{positionScale.toFixed(2)}×</output>
      </div>

      <div className="oa-tel__param" data-control="rotation-scale">
        <label htmlFor="oa-tel-rotation-scale">회전 스케일 (rotation_scale)</label>
        <input
          id="oa-tel-rotation-scale"
          type="range"
          data-field="rotation-scale"
          min={scale.rotationScaleMin}
          max={scale.rotationScaleMax}
          step={0.05}
          value={rotationScale}
          disabled={disabled}
          onChange={(event) => {
            const next = Number(event.target.value);
            setRotationScale(next);
            onRotationScale(next);
          }}
        />
        <output data-field="rotation-scale-value">{rotationScale.toFixed(2)}×</output>
      </div>

      <p className="oa-tel__hint">
        회전은 위치와 독립: joint6 리밋이 ±45°(±0.785 rad)로 좁아 1:1 매핑은 상시 충돌하므로 회전만 좁힌다.
      </p>
    </section>
  );
}
