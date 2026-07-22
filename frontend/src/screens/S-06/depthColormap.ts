// Depth colormap rendering (CG-G-S06d).
//
// A depth tile is never shown as raw millimetres — it is rendered as a colormap
// so near/far is legible, matching the backend preview's COLORMAP_JET depth
// encoding (WP-3B-06). The 0 mm value is the "no measurement" sentinel, never a
// zero distance (CTR-PRIM depth dtype uint16 mm; `06` §2.4 FR-CAM-038), so it
// maps to a distinct invalid colour rather than the near end of the ramp. This
// is display-only: the screen colourmaps a depth sample the backend provides and
// computes no depth itself.

// The value a uint16 mm depth pixel carries when the sensor made no measurement.
// Mirrors CTR-PRIM / `06` §2.4 DEPTH_NO_MEASUREMENT_MM; the contract test pins it.
export const DEPTH_NO_MEASUREMENT_MM = 0;

// The colour a no-measurement pixel is drawn in, kept clearly outside the JET
// ramp so an operator never reads "no data" as "very near".
export const DEPTH_INVALID_COLOR = "#3a3f44";

export interface Rgb {
  r: number;
  g: number;
  b: number;
}

// A JET-family ramp: blue (far/low) → cyan → green → yellow → red (near/high),
// matching cv2.COLORMAP_JET closely enough for a legible preview. `t` is clamped
// to [0, 1].
export function jetColor(t: number): Rgb {
  const clamped = t < 0 ? 0 : t > 1 ? 1 : t;
  const four = clamped * 4;
  const r = Math.round(255 * clampUnit(Math.min(four - 1.5, -four + 4.5)));
  const g = Math.round(255 * clampUnit(Math.min(four - 0.5, -four + 3.5)));
  const b = Math.round(255 * clampUnit(Math.min(four + 0.5, -four + 2.5)));
  return { r, g, b };
}

function clampUnit(value: number): number {
  return value < 0 ? 0 : value > 1 ? 1 : value;
}

// The CSS colour for one depth pixel. A no-measurement pixel gets the invalid
// colour; every other pixel is normalised into [depthMinMm, depthMaxMm] and run
// through the JET ramp. Nearer (smaller mm) reads hot, matching the preview.
export function depthPixelColor(mm: number, depthMinMm: number, depthMaxMm: number): string {
  if (mm === DEPTH_NO_MEASUREMENT_MM) {
    return DEPTH_INVALID_COLOR;
  }
  const span = depthMaxMm - depthMinMm;
  const normalized = span <= 0 ? 0 : (mm - depthMinMm) / span;
  // Invert so near = hot (red), far = cool (blue), as an operator expects.
  const { r, g, b } = jetColor(1 - normalized);
  return `rgb(${r}, ${g}, ${b})`;
}

// Map a row-major depth sample to per-cell CSS colours for the tile grid. The
// range defaults to the min/max of the valid (non-sentinel) pixels so a legible
// spread is shown even when the fixture uses a narrow band.
export function depthGridColors(
  depthMm: readonly number[],
  depthMinMm?: number,
  depthMaxMm?: number,
): string[] {
  const valid = depthMm.filter((mm) => mm !== DEPTH_NO_MEASUREMENT_MM);
  const min = depthMinMm ?? (valid.length > 0 ? Math.min(...valid) : 0);
  const max = depthMaxMm ?? (valid.length > 0 ? Math.max(...valid) : 1);
  return depthMm.map((mm) => depthPixelColor(mm, min, max));
}
