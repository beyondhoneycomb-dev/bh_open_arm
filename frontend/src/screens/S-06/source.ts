// The inputs the camera screen renders from, and the intents it emits. The
// screen is a window onto CAM (`06`): every value it shows — the registered
// camera set (via `observation_features`), each camera's configured geometry,
// the live stream stats, the record drop rate, the preview counters, the depth
// sample, the five-method hand-eye result, and the PG-CAM-001 / PG-DEPTH-001 gate
// state — originates in the backend. The screen sends user intent (toggle a
// camera's preview, toggle the master preview switch, adjust resolution/fps) and
// decides no domain truth: no tile-count constant, no unit conversion, no
// hand-eye method adoption, no drop-rate recomputation.
//
// This WP is AI-offline and verified against fixtures, so `defaultCameraScreenSource`
// stands in for a backend that is not connected, exactly as the safety screen's
// `defaultSafetyScreenSource` does. The default is honest about reality: the 3C
// hardware gates (PG-CAM-001 / PG-DEPTH-001) have NOT landed, so both read
// "pending" — the graceful state the screen must render without fabricating a
// verdict (02d graceful-3C rule).

import { imageFeatureKey, type CameraChannel } from "../../ws/envelope";
import type { StreamStats } from "../../ws/streamMeter";
import { HAND_EYE_METHOD_NAMES, type HandEyeMethodRow, type HandEyeView } from "./handEye";
import type { CameraGateState } from "./camGate";

// The preview pipe's per-outcome counters (WP-3B-06 `PreviewCounters`). Kept
// apart because they mean different things: encode/transmit is work done, a drop
// is healthy backpressure shedding, a skip is a camera that gave no frame. These
// are the PREVIEW path only and never the recording drop (WP-3C-03 isolation).
export interface PreviewCounters {
  encoded: number;
  transmitted: number;
  dropped: number;
  skipped: number;
}

// One camera's runtime state, keyed by its CTR-PRIM slot in `CameraScreenSource`.
export interface CameraRuntime {
  // Configured geometry from the backend `CameraSpec` (CTR-CAM). A null on any
  // field means registered-but-unconfigured — collection cannot start, and the
  // metric target is unknown rather than a fabricated default.
  width: number | null;
  height: number | null;
  fps: number | null;
  // This camera's preview switch (WP-3B-06). Independent of recording: a preview
  // may be OFF while recording continues (CG-G-S06c).
  previewEnabled: boolean;
  // The live RGB stream stats from the shared WS StreamMeter (foundation).
  rgbStats: StreamStats;
  // The live depth stream stats, or null when this camera carries no depth.
  depthStats: StreamStats | null;
  // The backend record (capture) drop fraction (DropReport). Invariant to preview
  // state — the WP-3C-03 isolation guarantee the screen renders but does not own.
  recordDropFraction: number;
  // The preview pipe's per-outcome counters for this camera.
  preview: PreviewCounters;
  // A small row-major depth sample (uint16 mm) the screen colormaps for the depth
  // tile (CG-G-S06d), or null for an RGB-only camera. 0 mm = no measurement.
  depthSampleMm: readonly number[] | null;
  depthSampleWidth: number;
}

export interface CameraScreenSource {
  // The authoritative keyset the tile grid is derived from (CG-G-S06a). Adding a
  // camera adds its `observation.images.<slot>` (and optional `_depth`) key here.
  readonly observationFeatures: readonly string[];
  // Per-slot runtime, keyed by the CTR-PRIM slot key.
  readonly cameras: Readonly<Record<string, CameraRuntime>>;
  // Per-camera hand-eye results (five methods each, no single adopted answer).
  readonly handEye: readonly HandEyeView[];
  // The 3C hardware-gate state (PG-CAM-001 / PG-DEPTH-001), rendered as-is.
  readonly gates: CameraGateState;
  // The service-wide preview master switch (WP-3B-06 `PreviewService`).
  readonly masterPreviewEnabled: boolean;
}

// User intents the screen emits. Each asks the backend to change state; the
// backend enforces, the screen renders the result. Defaults are no-ops so the
// offline screen is inert but complete.
export interface CameraScreenIntents {
  // Toggle one camera's preview without touching recording (CG-G-S06c).
  onToggleCameraPreview: (slot: string, enabled: boolean) => void;
  // Toggle the preview master switch. OFF stops every preview at zero cost.
  onToggleMasterPreview: (enabled: boolean) => void;
  // Ask the backend to reconfigure a camera's resolution/fps (CTR-CAM validates).
  onConfigureCamera: (slot: string, width: number, height: number, fps: number) => void;
}

export function noopIntents(): CameraScreenIntents {
  return {
    onToggleCameraPreview: () => {},
    onToggleMasterPreview: () => {},
    onConfigureCamera: () => {},
  };
}

// A deterministic rolling stat for a channel: `fps` near a target with a modest
// jitter and drop count. The fixture carries no timing math — it states the
// numbers a meter would have produced, so the WARN classification is exercised
// on known inputs.
function demoStats(channel: string, fps: number, jitterMs: number, dropCount: number): StreamStats {
  return { channel, fps, jitterMs, dropCount, sampleCount: Math.round(fps) };
}

// The five method rows for a hand-eye result. Residuals are illustrative backend
// numbers, all five present (never collapsed) so CG-G-S06f renders the full set.
function demoMethods(): HandEyeMethodRow[] {
  const residuals: Record<string, [number, number]> = {
    TSAI: [0.42, 1.8],
    PARK: [0.31, 1.2],
    HORAUD: [0.33, 1.3],
    ANDREFF: [0.29, 1.1],
    DANIILIDIS: [0.3, 1.15],
  };
  return HAND_EYE_METHOD_NAMES.map((method) => ({
    method,
    residualRotationDeg: residuals[method][0],
    residualTranslationMm: residuals[method][1],
  }));
}

function demoDeviations(): HandEyeView["deviations"] {
  // A single representative pair; the compare view renders whatever set arrives.
  return [
    { methodA: "TSAI", methodB: "PARK", rotationDeg: 0.6, translationMm: 2.4 },
    { methodA: "PARK", methodB: "DANIILIDIS", rotationDeg: 0.12, translationMm: 0.5 },
  ];
}

// A tiny 8×6 depth sample in millimetres: a near-to-far gradient with a couple of
// no-measurement (0 mm) holes, so the colormap and its invalid-colour path both
// render on a known input (CG-G-S06d).
function demoDepthSample(): number[] {
  const width = 8;
  const height = 6;
  const sample: number[] = [];
  for (let row = 0; row < height; row += 1) {
    for (let col = 0; col < width; col += 1) {
      const isHole = (row === 2 && col === 5) || (row === 4 && col === 1);
      sample.push(isHole ? 0 : 400 + (row * width + col) * 60);
    }
  }
  return sample;
}

// The standing offline fixture: two arm wrist cameras (one RGB-only, one RGB+D)
// plus a top-level front camera, the 3C gates pending, and one hand-eye result.
export function defaultCameraScreenSource(): CameraScreenSource {
  const leftWrist = "left_wrist";
  const rightWrist = "right_wrist";
  const front = "front";

  const observationFeatures = [
    "observation.state",
    "action",
    imageFeatureKey(leftWrist, "rgb" as CameraChannel),
    imageFeatureKey(rightWrist, "rgb" as CameraChannel),
    imageFeatureKey(rightWrist, "depth" as CameraChannel),
    imageFeatureKey(front, "rgb" as CameraChannel),
  ];

  const cameras: Record<string, CameraRuntime> = {
    [leftWrist]: {
      width: 640,
      height: 480,
      fps: 30,
      previewEnabled: true,
      rgbStats: demoStats(imageFeatureKey(leftWrist, "rgb" as CameraChannel), 29.4, 1.6, 2),
      depthStats: null,
      recordDropFraction: 0.004,
      preview: { encoded: 512, transmitted: 508, dropped: 4, skipped: 0 },
      depthSampleMm: null,
      depthSampleWidth: 0,
    },
    [rightWrist]: {
      width: 640,
      height: 480,
      fps: 30,
      // Preview intentionally OFF while recording — the CG-G-S06c standing case.
      previewEnabled: false,
      rgbStats: demoStats(imageFeatureKey(rightWrist, "rgb" as CameraChannel), 30.0, 1.1, 0),
      depthStats: demoStats(imageFeatureKey(rightWrist, "depth" as CameraChannel), 29.8, 1.3, 1),
      recordDropFraction: 0.006,
      preview: { encoded: 0, transmitted: 0, dropped: 0, skipped: 0 },
      depthSampleMm: demoDepthSample(),
      depthSampleWidth: 8,
    },
    [front]: {
      width: 1280,
      height: 720,
      fps: 30,
      previewEnabled: true,
      // Below the 95% floor (30 × 0.95 = 28.5) → WARN exercised on a known input.
      rgbStats: demoStats(imageFeatureKey(front, "rgb" as CameraChannel), 26.0, 3.4, 41),
      depthStats: null,
      recordDropFraction: 0.031,
      preview: { encoded: 460, transmitted: 402, dropped: 58, skipped: 0 },
      depthSampleMm: null,
      depthSampleWidth: 0,
    },
  };

  const handEye: HandEyeView[] = [
    {
      slot: rightWrist,
      setup: "eye_in_hand",
      samplePoseCount: 12,
      methods: demoMethods(),
      deviations: demoDeviations(),
      stale: false,
      capturedLabel: "최근 캘리브 (12 포즈)",
    },
    {
      slot: front,
      setup: "eye_to_hand",
      samplePoseCount: 9,
      methods: demoMethods(),
      deviations: demoDeviations(),
      // Stale → frustum shown stale (CG-G-S06g).
      stale: true,
      capturedLabel: "이전 세션 캘리브 (재수집 필요)",
    },
  ];

  return {
    observationFeatures,
    cameras,
    handEye,
    gates: {
      // The 3C hardware gates have not landed — pending, not fabricated.
      pgCam001: "pending",
      pgDepth001: "pending",
      blockedSlots: [],
    },
    masterPreviewEnabled: true,
  };
}
