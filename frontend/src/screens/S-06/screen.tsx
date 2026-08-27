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
import { DeviceAssignmentPanel } from "./DeviceAssignmentPanel";
import { FrustumStatus } from "./FrustumStatus";
import { HandEyeCompareView } from "./HandEyeCompareView";
import { PreviewIsolationPanel } from "./PreviewIsolationPanel";
import { StreamStatsView } from "./StreamStatsView";
import { TilePreviewGrid } from "./TilePreviewGrid";
import { depthLayerEnabled, depthNote } from "./camGate";
import { deriveTiles } from "./tiles";
import {
  defaultCameraScreenSource,
  noopIntents,
  type CameraScreenIntents,
  type CameraScreenSource,
} from "./source";
import { useCameraDevices } from "./useCameraDevices";

interface CameraScreenProps {
  source?: CameraScreenSource;
  intents?: CameraScreenIntents;
}

export default function CameraScreen({ source, intents }: CameraScreenProps) {
  // A caller that supplied a source is driving this screen itself — a fixture, a
  // test, a later integration wave. Only the unsupplied case talks to the backend,
  // so a fixture render never reaches for a device.
  const live = useCameraDevices(source === undefined);
  const rendered = source ?? defaultCameraScreenSource();
  const acting = intents ?? noopIntents();
  const depthOn = depthLayerEnabled(rendered.gates);
  const depthReducedNote = depthNote(rendered.gates);
  // The slots on offer are the registered ones, derived the same way the tiles
  // are (CG-G-S06a). A hardcoded slot list here would let the panel offer a slot
  // the robot does not have, and the assignment would fail at the backend.
  const derivedSlots = deriveTiles(rendered.observationFeatures).map((tile) => tile.slot);
  // The backend's registered set once it has answered. It is what the assignment is validated
  // against, so offering anything else would offer a slot the PUT refuses.
  const slots = live.scan?.slots ?? derivedSlots;
  const discovered = live.scan?.devices ?? (source === undefined ? [] : rendered.discovered);

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

      {live.error === null ? null : (
        <p className="oa-cam__device-error" role="alert" data-device-error="true">
          {live.error}
        </p>
      )}

      <DeviceAssignmentPanel
        discovered={discovered}
        slots={slots}
        onRescanDevices={source === undefined ? live.rescan : acting.onRescanDevices}
        onAssignDevice={source === undefined ? live.assign : acting.onAssignDevice}
        onReleaseDevice={source === undefined ? live.release : acting.onReleaseDevice}
      />

      <TilePreviewGrid
        observationFeatures={rendered.observationFeatures}
        cameras={rendered.cameras}
        gates={rendered.gates}
      />

      <StreamStatsView cameras={rendered.cameras} />

      <PreviewIsolationPanel
        cameras={rendered.cameras}
        masterPreviewEnabled={rendered.masterPreviewEnabled}
        onToggleCameraPreview={acting.onToggleCameraPreview}
        onToggleMasterPreview={acting.onToggleMasterPreview}
      />

      <div className="oa-cam__grid">
        <HandEyeCompareView results={rendered.handEye} />
        <FrustumStatus results={rendered.handEye} depthLayerEnabled={depthOn} />
      </div>
    </div>
  );
}
