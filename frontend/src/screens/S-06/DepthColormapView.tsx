// Renders a depth sample as a colormap grid (CG-G-S06d). The screen colormaps a
// backend-provided depth sample (uint16 mm); it computes no depth. The 0 mm
// no-measurement sentinel is drawn in the distinct invalid colour, never the near
// end of the ramp, so "no data" never reads as "very near".

import { depthGridColors } from "./depthColormap";

interface DepthColormapViewProps {
  slot: string;
  depthMm: readonly number[];
  width: number;
}

export function DepthColormapView({ slot, depthMm, width }: DepthColormapViewProps) {
  const colors = depthGridColors(depthMm);
  return (
    <div className="oa-cam__depth" data-depth-colormap={slot}>
      <div
        className="oa-cam__depth-grid"
        style={{ gridTemplateColumns: `repeat(${width}, 1fr)` }}
        role="img"
        aria-label={`${slot} depth colormap`}
      >
        {colors.map((color, index) => (
          <span
            key={index}
            className="oa-cam__depth-cell"
            style={{ background: color }}
            data-depth-cell={index}
          />
        ))}
      </div>
      <p className="oa-cam__depth-legend">
        컬러맵(JET) · 근거리=적색 · 원거리=청색 · 무측정(0&nbsp;mm)=회색
      </p>
    </div>
  );
}
