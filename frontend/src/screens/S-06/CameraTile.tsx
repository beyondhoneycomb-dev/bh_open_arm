// One camera tile (CG-G-S06b, CG-G-S06c, CG-G-S06d, graceful 3C gate). A tile
// shows BOTH the operator UI label and the dataset key it maps to, the arm-prefix
// note when the slot carries one, the live RGB preview area (or a blocked/pending
// note from the 3C gate), and the depth colormap when the camera carries depth
// and the depth layer is enabled. It renders backend state; it decides nothing.

import { DepthColormapView } from "./DepthColormapView";
import { tileGate, type CameraGateState } from "./camGate";
import { splitArm, type CameraTileModel } from "./tiles";
import type { CameraRuntime } from "./source";

interface CameraTileProps {
  tile: CameraTileModel;
  runtime: CameraRuntime | undefined;
  gates: CameraGateState;
  depthLayerEnabled: boolean;
}

function armPrefixNote(slot: string): string | null {
  const { arm } = splitArm(slot);
  if (arm === null) {
    return null;
  }
  return `${arm}_ 접두사 자동 부착 → ${slot}`;
}

function geometryLabel(runtime: CameraRuntime | undefined): string {
  if (runtime === undefined || runtime.width === null || runtime.height === null) {
    return "미구성 (해상도·fps 필요)";
  }
  return `${runtime.width}×${runtime.height} @ ${runtime.fps ?? "?"}fps`;
}

export function CameraTile({ tile, runtime, gates, depthLayerEnabled }: CameraTileProps) {
  const gate = tileGate(tile.slot, gates);
  const prefixNote = armPrefixNote(tile.slot);
  const showDepth = tile.hasDepth && depthLayerEnabled && runtime?.depthSampleMm != null;

  return (
    <article
      className="oa-cam__tile"
      data-tile-slot={tile.slot}
      data-tile-disposition={gate.disposition}
    >
      <header className="oa-cam__tile-head">
        <span className="oa-cam__tile-label" data-tile-label={tile.slot}>
          {tile.uiLabel}
        </span>
        <code className="oa-cam__tile-key" data-dataset-key={tile.slot}>
          {tile.datasetKey}
        </code>
      </header>

      {prefixNote === null ? null : (
        <p className="oa-cam__tile-prefix" data-arm-prefix-note={tile.slot}>
          {prefixNote}
        </p>
      )}

      {gate.disposition === "blocked" ? (
        <div className="oa-cam__tile-blocked" data-tile-blocked={tile.slot} role="status">
          {gate.note}
        </div>
      ) : (
        <div className="oa-cam__tile-body">
          <div className="oa-cam__tile-preview" data-tile-preview={tile.slot}>
            {runtime?.previewEnabled ? (
              <span className="oa-cam__tile-live">RGB 프리뷰 (WS 바이너리 JPEG)</span>
            ) : (
              <span className="oa-cam__tile-off" data-preview-off={tile.slot}>
                프리뷰 OFF (기록은 계속)
              </span>
            )}
          </div>
          {showDepth ? (
            <DepthColormapView
              slot={tile.slot}
              depthMm={runtime!.depthSampleMm!}
              width={runtime!.depthSampleWidth}
            />
          ) : null}
        </div>
      )}

      {gate.disposition === "pending" ? (
        <p className="oa-cam__tile-pending" data-tile-pending={tile.slot} role="status">
          {gate.note}
        </p>
      ) : null}

      <footer className="oa-cam__tile-foot">
        <span className="oa-cam__tile-geom">{geometryLabel(runtime)}</span>
        {tile.hasDepth ? (
          <span className="oa-cam__badge oa-cam__badge--depth">
            {depthLayerEnabled ? "RGB+D" : "RGB-only(축소)"}
          </span>
        ) : (
          <span className="oa-cam__badge oa-cam__badge--rgb">RGB</span>
        )}
      </footer>
    </article>
  );
}
