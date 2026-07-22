// S-06 camera screen (route /cameras). The window onto CAM (`06`): it renders the
// backend's camera state — the tile grid derived from `observation_features`, the
// stream stats, the depth colormap, the five-method hand-eye compare, the frustum
// trust status, and the preview/recording isolation — and emits operator intent.
// It owns no domain truth: no tile-count constant, no unit conversion, no
// hand-eye method adoption, no drop-rate recompute (the camera canon, the fps
// targets, the drop rates, and the hand-eye solve all live in the backend).
//
// Like the safety screen, it renders from a `source` prop with an offline default
// fixture and calls intent callbacks that default to no-ops, so the WP is
// verifiable against fixtures without a backend (AI-offline). The screen resolver
// mounts it with no props; a later integration wave wires live WS state in.
//
// The gates this screen keeps, and where each is kept:
//   - CG-G-S06a tile count runtime-derived, no constant  → tiles / TilePreviewGrid
//   - CG-G-S06b every tile shows UI label AND dataset key → CameraTile
//   - CG-G-S06c preview ⟂ record drop, OFF while recording → PreviewIsolationPanel
//   - CG-G-S06d depth tile renders as a colormap           → DepthColormapView
//   - CG-G-S06e FPS/jitter/drop, WARN under 95% of target  → StreamStatsView / metrics
//   - CG-G-S06f hand-eye 5 methods, no single-adopt UI     → HandEyeCompareView / handEye
//   - CG-G-S06g frustum shown stale when hand-eye is stale → FrustumStatus
//   - PG-CAM-001 / PG-DEPTH-001 rendered as-is (pending)   → camGate

import "./screen.css";
import { FrustumStatus } from "./FrustumStatus";
import { HandEyeCompareView } from "./HandEyeCompareView";
import { PreviewIsolationPanel } from "./PreviewIsolationPanel";
import { StreamStatsView } from "./StreamStatsView";
import { TilePreviewGrid } from "./TilePreviewGrid";
import { depthLayerEnabled, depthNote } from "./camGate";
import {
  defaultCameraScreenSource,
  noopIntents,
  type CameraScreenIntents,
  type CameraScreenSource,
} from "./source";

interface CameraScreenProps {
  source?: CameraScreenSource;
  intents?: CameraScreenIntents;
}

export default function CameraScreen({
  source = defaultCameraScreenSource(),
  intents = noopIntents(),
}: CameraScreenProps) {
  const depthOn = depthLayerEnabled(source.gates);
  const depthReducedNote = depthNote(source.gates);

  return (
    <div className="oa-cam">
      <header className="oa-cam__head">
        <span className="oa-cam__id">/cameras</span>
        <h1 className="oa-cam__title">카메라</h1>
      </header>

      {depthReducedNote === null ? null : (
        <p className="oa-cam__gate-banner" role="status" data-depth-gate-note="true">
          {depthReducedNote}
        </p>
      )}

      <TilePreviewGrid
        observationFeatures={source.observationFeatures}
        cameras={source.cameras}
        gates={source.gates}
      />

      <StreamStatsView cameras={source.cameras} />

      <PreviewIsolationPanel
        cameras={source.cameras}
        masterPreviewEnabled={source.masterPreviewEnabled}
        onToggleCameraPreview={intents.onToggleCameraPreview}
        onToggleMasterPreview={intents.onToggleMasterPreview}
      />

      <div className="oa-cam__grid">
        <HandEyeCompareView results={source.handEye} />
        <FrustumStatus results={source.handEye} depthLayerEnabled={depthOn} />
      </div>
    </div>
  );
}
