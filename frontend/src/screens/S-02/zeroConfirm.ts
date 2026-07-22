// Per-joint current-vs-rest delta for the zero-confirm view (CG-G-S02d,
// FR-GUI-084). Before the operator confirms a re-zero they must see how far each
// joint is from the URDF rest pose. Both numbers are BACKEND numbers in radians —
// the live telemetry pose and the URDF rest pose — and the delta is a pure display
// subtraction. This module invents NO closeness threshold and makes NO decision:
// judging "close enough to rest" is the operator's, manually, via the double
// confirm. A screen-side threshold would be a second source of truth for the zero
// policy the backend owns. The value is shown in radians; no deg<->rad conversion.

export interface JointDelta {
  joint: string;
  currentRad: number;
  restRad: number;
  // currentRad - restRad, in radians. Display only.
  deltaRad: number;
}

// Compute the per-joint delta over the URDF joint set. A joint missing from either
// pose is reported with a non-finite delta so the row reads as "unknown" rather
// than a fabricated 0 — the same reason the viewport rejects a partial frame
// instead of filling gaps with 0 (get_observation() fills missing motors with 0).
export function perJointDelta(
  currentRad: Readonly<Record<string, number>>,
  restRad: Readonly<Record<string, number>>,
  jointNames: readonly string[],
): JointDelta[] {
  return jointNames.map((joint) => {
    const current = currentRad[joint];
    const rest = restRad[joint];
    const known = Number.isFinite(current) && Number.isFinite(rest);
    return {
      joint,
      currentRad: current,
      restRad: rest,
      deltaRad: known ? current - rest : Number.NaN,
    };
  });
}

// The largest absolute delta across joints, or NaN when any joint is unknown. A
// magnitude the view can surface next to the table; still not a gate — the
// operator decides whether it is acceptable.
export function maxAbsDelta(deltas: readonly JointDelta[]): number {
  let max = 0;
  for (const delta of deltas) {
    if (!Number.isFinite(delta.deltaRad)) {
      return Number.NaN;
    }
    max = Math.max(max, Math.abs(delta.deltaRad));
  }
  return max;
}
