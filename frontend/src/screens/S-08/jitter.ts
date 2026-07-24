// Capture jitter, read from the capture_ts sidecar — never from the synthetic grid
// (CG-G-S08c). The per-frame `timestamp` column is `frame_index / fps`: a perfectly
// even grid whose successive differences are all exactly `1/fps`, so reading jitter
// off it shows jitter as a flat zero, always. Real capture jitter lives only in the
// backend `capture_ts` sidecar (nanosecond grab instants); this module turns that
// sidecar into the inter-frame interval spread the jitter view renders.
//
// This is presentation over the sidecar (interval spread, in milliseconds), the same
// altitude as the foundation StreamMeter or S-06's metrics — it re-sources no domain
// truth. The one rule it enforces is the source: jitter is computed from
// `captureTsNs`, and the synthetic `timestamp` grid is never its input.

import type { CaptureTsSidecar } from "./types";

const NS_PER_MS = 1_000_000;

// One slot's capture-interval statistics, in milliseconds. `meanIntervalMs` is the
// average grab-to-grab spacing; `jitterMs` is the spread of that spacing (max minus
// min interval), the figure an operator reads as "how uneven was capture". A slot with
// fewer than two samples has no interval, reported as zeroes rather than fabricated.
export interface CaptureJitterStat {
  slot: string;
  sampleCount: number;
  meanIntervalMs: number;
  jitterMs: number;
  maxIntervalMs: number;
  minIntervalMs: number;
}

// Successive differences of a nanosecond capture-instant series, in milliseconds.
function intervalsMs(captureTsNs: readonly number[]): number[] {
  const intervals: number[] = [];
  for (let i = 1; i < captureTsNs.length; i += 1) {
    intervals.push((captureTsNs[i] - captureTsNs[i - 1]) / NS_PER_MS);
  }
  return intervals;
}

// Compute one slot's capture-interval statistics from its capture_ts sidecar.
export function jitterForSidecar(sidecar: CaptureTsSidecar): CaptureJitterStat {
  const intervals = intervalsMs(sidecar.captureTsNs);
  if (intervals.length === 0) {
    return {
      slot: sidecar.slot,
      sampleCount: sidecar.captureTsNs.length,
      meanIntervalMs: 0,
      jitterMs: 0,
      maxIntervalMs: 0,
      minIntervalMs: 0,
    };
  }
  const sum = intervals.reduce((acc, value) => acc + value, 0);
  const max = Math.max(...intervals);
  const min = Math.min(...intervals);
  return {
    slot: sidecar.slot,
    sampleCount: sidecar.captureTsNs.length,
    meanIntervalMs: sum / intervals.length,
    jitterMs: max - min,
    maxIntervalMs: max,
    minIntervalMs: min,
  };
}

// Compute capture-interval statistics for every camera slot's sidecar.
export function jitterForSidecars(
  sidecars: readonly CaptureTsSidecar[],
): CaptureJitterStat[] {
  return sidecars.map(jitterForSidecar);
}
