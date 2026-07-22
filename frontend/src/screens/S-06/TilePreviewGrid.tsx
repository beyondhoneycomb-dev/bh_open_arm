// The tile-preview grid (CG-G-S06a). The tile set is derived from the backend
// `observation_features` keyset at render time — there is no tile-count constant
// anywhere — so a camera add/remove is followed automatically with no code
// change. The grid is CSS auto-fill, so its column count follows the derived tile
// count rather than a hardcoded layout.

import { CameraTile } from "./CameraTile";
import { deriveTiles } from "./tiles";
import { depthLayerEnabled, type CameraGateState } from "./camGate";
import type { CameraRuntime } from "./source";

interface TilePreviewGridProps {
  observationFeatures: readonly string[];
  cameras: Readonly<Record<string, CameraRuntime>>;
  gates: CameraGateState;
}

export function TilePreviewGrid({ observationFeatures, cameras, gates }: TilePreviewGridProps) {
  const tiles = deriveTiles(observationFeatures);
  const depthOn = depthLayerEnabled(gates);
  return (
    <section className="oa-cam__panel" aria-labelledby="oa-cam-tiles-title">
      <div className="oa-cam__panel-head">
        <h2 id="oa-cam-tiles-title" className="oa-cam__panel-title">
          타일 프리뷰
        </h2>
        <span className="oa-cam__tile-count" data-tile-count={tiles.length}>
          {tiles.length} 타일 (observation_features 런타임 유도)
        </span>
      </div>
      {tiles.length === 0 ? (
        <p className="oa-cam__empty" role="status">
          등록된 카메라 없음 — observation_features에 카메라 키가 없다
        </p>
      ) : (
        <div className="oa-cam__tile-grid">
          {tiles.map((tile) => (
            <CameraTile
              key={tile.slot}
              tile={tile}
              runtime={cameras[tile.slot]}
              gates={gates}
              depthLayerEnabled={depthOn}
            />
          ))}
        </div>
      )}
    </section>
  );
}
