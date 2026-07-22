// CG-G-S09e: the sim-vs-real ghost overlay must make the two visually UNMISTAKABLE.
// Real is drawn solid and opaque; sim is drawn as a translucent, dashed ghost in a
// different hue. Both share the one 3D viewport (WP-G-02) as their base; this panel
// adds the legend and the per-layer swatches that carry the distinction, whose
// dimensions are proven all-distinct by ghostLayersAreDistinct() in simDomain.

import { ViewportPanel } from "../../viewport";
import type { ViewportSource } from "../../viewport";
import { GHOST_LAYER_STYLES, type ControlTarget } from "./simDomain";

interface GhostOverlayProps {
  viewport: ViewportSource;
}

const LAYER_ORDER: readonly ControlTarget[] = ["real", "sim"];

export function GhostOverlay({ viewport }: GhostOverlayProps) {
  return (
    <section className="oa-sim__ghost" aria-labelledby="oa-sim-ghost-title">
      <h2 id="oa-sim-ghost-title" className="oa-sim__section-title">
        sim vs real 고스트 오버레이
      </h2>

      <ul className="oa-sim__ghost-legend" aria-label="고스트 오버레이 범례">
        {LAYER_ORDER.map((target) => {
          const style = GHOST_LAYER_STYLES[target];
          return (
            <li
              key={target}
              className="oa-sim__ghost-legend-item"
              data-layer={target}
              data-outline={style.outline}
            >
              <span
                className="oa-sim__ghost-swatch"
                data-layer={target}
                style={{
                  backgroundColor: style.colorToken,
                  opacity: style.opacity,
                  borderStyle: style.outline,
                }}
                aria-hidden="true"
              />
              <span className="oa-sim__ghost-legend-label">{style.label}</span>
            </li>
          );
        })}
      </ul>

      <div className="oa-sim__ghost-viewport">
        <ViewportPanel source={viewport} />
      </div>
    </section>
  );
}
