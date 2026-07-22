// Stream-metric WARN evaluation (CG-G-S06e).
//
// The three metrics — FPS, jitter_ms, drop — are produced by the shared WS
// StreamMeter (foundation, CG-G-01e); this module does not recompute them. It
// applies the display classification NFR-CAM-006 states: an achieved FPS below
// 95% of the configured target, or a drop fraction over the recording ceiling,
// is surfaced as WARN. The 0.95 and 2% figures are the NFR-CAM-006 / NFR-CAM-003
// reference lines the screen RENDERS a backend number against; the screen owns
// neither the target (CTR-CAM `CameraSpec.fps`) nor the PASS verdict (PG-CAM-001
// decides that on real hardware). An unconfigured camera has no target, so its
// level is "unknown" rather than a fabricated OK.

import type { StreamStats } from "../../ws/streamMeter";

// NFR-CAM-006: achieved FPS must stay at or above target × 0.95.
export const FPS_WARN_RATIO = 0.95;
// NFR-CAM-003 / NFR-CAM-006: the recording drop-rate ceiling is 2%.
export const DROP_WARN_FRACTION = 0.02;

export type MetricLevel = "ok" | "warn" | "unknown";

export interface StreamMetricView {
  channel: string;
  fps: number;
  jitterMs: number;
  dropCount: number;
  // The backend record-drop fraction for this stream (DropReport), rendered
  // beside the live meter counts; independent of preview state (WP-3C-03).
  recordDropFraction: number;
  // The configured target FPS from the backend CameraSpec, or null when the
  // camera is registered but not yet configured.
  targetFps: number | null;
  level: MetricLevel;
}

// Whether a stream's achieved FPS is below the NFR-CAM-006 floor of its target.
export function fpsBelowFloor(fps: number, targetFps: number): boolean {
  return fps < targetFps * FPS_WARN_RATIO;
}

// Classify one stream. WARN when the achieved FPS is under 95% of target or the
// record drop fraction is over 2%; UNKNOWN when there is no configured target.
export function evaluateStream(
  stats: StreamStats,
  targetFps: number | null,
  recordDropFraction: number,
): StreamMetricView {
  let level: MetricLevel;
  if (targetFps === null) {
    level = "unknown";
  } else if (fpsBelowFloor(stats.fps, targetFps) || recordDropFraction > DROP_WARN_FRACTION) {
    level = "warn";
  } else {
    level = "ok";
  }
  return {
    channel: stats.channel,
    fps: stats.fps,
    jitterMs: stats.jitterMs,
    dropCount: stats.dropCount,
    recordDropFraction,
    targetFps,
    level,
  };
}
