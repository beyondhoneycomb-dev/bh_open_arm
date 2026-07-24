// Jitter is read from capture_ts, never the synthetic grid (CG-G-S08c). The two
// assertions that matter are opposites on purpose: a capture_ts series built from an
// EVEN grid (frame_index/fps in nanoseconds) has zero interval spread — which is
// exactly why the synthetic timestamp can never be a jitter source — while a real
// capture_ts series with uneven grab spacing reports a non-zero spread. Feeding the
// synthetic grid into the jitter view would show jitter flat at zero forever.

import { describe, expect, it } from "vitest";

import { jitterForSidecar } from "./jitter";
import type { CaptureTsSidecar } from "./types";

const NS_PER_MS = 1_000_000;

// Build a nanosecond capture series from millisecond intervals.
function series(slot: string, base: number, intervalsMs: number[]): CaptureTsSidecar {
  const captureTsNs = [base];
  let cursor = base;
  for (const ms of intervalsMs) {
    cursor += ms * NS_PER_MS;
    captureTsNs.push(cursor);
  }
  return { slot, captureTsNs };
}

describe("jitterForSidecar (CG-G-S08c)", () => {
  it("reports zero jitter for a perfectly even grid (the synthetic-timestamp trap)", () => {
    // An even 30 fps grid: every interval is 1000/30 ms. This is what the synthetic
    // `timestamp` column looks like — and its jitter is identically zero.
    const even = series("grid", 0, [1000 / 30, 1000 / 30, 1000 / 30, 1000 / 30]);
    const stat = jitterForSidecar(even);
    expect(stat.jitterMs).toBeCloseTo(0, 6);
    expect(stat.meanIntervalMs).toBeCloseTo(1000 / 30, 6);
  });

  it("reports real spread for uneven capture instants", () => {
    const real = series("right_wrist", 1_000_000_000, [33.4, 33.1, 32.6, 34.8, 32.3]);
    const stat = jitterForSidecar(real);
    // spread = max(34.8) - min(32.3) = 2.5 ms, genuinely non-zero.
    expect(stat.jitterMs).toBeCloseTo(2.5, 5);
    expect(stat.maxIntervalMs).toBeCloseTo(34.8, 5);
    expect(stat.minIntervalMs).toBeCloseTo(32.3, 5);
    expect(stat.sampleCount).toBe(6);
  });

  it("reports zeroes for a slot with fewer than two samples rather than fabricating", () => {
    const stat = jitterForSidecar({ slot: "one", captureTsNs: [42] });
    expect(stat.jitterMs).toBe(0);
    expect(stat.meanIntervalMs).toBe(0);
    expect(stat.sampleCount).toBe(1);
  });
});
