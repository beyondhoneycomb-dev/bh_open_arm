// The drop-rate display bands the drop report flags an episode with (CG-G-S07d,
// FR-GUI-103). These are PRESENTATION thresholds, not a quality gate: 02b §5.2
// WP-3B-12 ⑥ leaves the recorder's quality bars to-be-decided / caller-supplied, so
// S-07 must not present its own number AS that gate. What these do is colour an
// episode's drop rate so an operator sees a run trending bad early — ~2% tolerated,
// ~5% is overload. The WS-transmit and capture rates are flagged SEPARATELY
// (CG-G-S07c); this module only turns a ratio into a band.

// ~2% of frames dropped is the tolerated ceiling; above it the episode is warned.
export const DROP_RATE_WARN = 0.02;
// ~5% of frames dropped signals overload; above it the episode is flagged overloaded.
export const DROP_RATE_OVERLOAD = 0.05;

export type DropFlag = "ok" | "warn" | "overload";

// The drop rate for a channel/side, 0 when there were no frames (an empty episode
// has no rate rather than a divide-by-zero). Pure display arithmetic over
// backend-supplied counts — the counts themselves are the backend's (WP-3B-12).
export function dropRate(drops: number, frames: number): number {
  return frames > 0 ? drops / frames : 0;
}

// The band a rate falls in. Uses `>` so exactly the tolerated ceiling is still ok.
export function flagForRate(rate: number): DropFlag {
  if (rate > DROP_RATE_OVERLOAD) {
    return "overload";
  }
  if (rate > DROP_RATE_WARN) {
    return "warn";
  }
  return "ok";
}

export function flagForCounts(drops: number, frames: number): DropFlag {
  return flagForRate(dropRate(drops, frames));
}
