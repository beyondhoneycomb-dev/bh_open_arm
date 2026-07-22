// Geometry for the residual plot, kept pure so the "same plot" invariant is
// testable without a DOM. CG-G-S12c requires the residual timeseries and its
// threshold to share one plot: splitting them across two views hides the moment
// the residual crosses the threshold, which is the only moment that matters.
//
// The invariant is enforced here by construction — the threshold line and the
// residual polyline are mapped through the SAME y-scale (`yForValue`), so the
// threshold sits at its true height relative to the samples. The residual values
// and the threshold are both backend facts (Nm); this module rescales them for
// drawing and does not convert units or re-derive the threshold.

export interface ResidualSample {
  // Backend monotonic timestamp (ms).
  tMonoMs: number;
  // GMO residual magnitude for this joint (Nm), as the backend computes it.
  valueNm: number;
}

export interface JointResidual {
  jointName: string;
  samples: readonly ResidualSample[];
  // Per-joint collision threshold the backend derived (FR-SAF-060). The GUI
  // renders this line; it does not compute the threshold.
  thresholdNm: number;
  // URDF effort limit for context (the threshold's design ceiling, §2.5).
  effortLimitNm: number;
}

export interface PlotPoint {
  x: number;
  y: number;
}

export interface ResidualPlotGeometry {
  width: number;
  height: number;
  // Residual polyline as an SVG points string.
  residualPoints: string;
  // Shared y-scale outputs: the positive and negative threshold lines sit here.
  thresholdY: number;
  negThresholdY: number;
  // Baseline (zero residual) in the same scale.
  zeroY: number;
  // Samples whose magnitude exceeds the backend threshold, in plot coordinates,
  // so a breach is marked on the same plot rather than inferred elsewhere.
  breachPoints: PlotPoint[];
  // Whether any sample breaches the threshold — drives the plot's breach styling.
  breached: boolean;
}

const DEFAULT_HEADROOM = 1.15;

// Map a residual value to a y coordinate under a symmetric ±yMax scale, y down.
function makeYScale(height: number, yMax: number): (valueNm: number) => number {
  const safeMax = yMax > 0 ? yMax : 1;
  return (valueNm: number) => {
    const normalized = (valueNm + safeMax) / (2 * safeMax);
    return height - normalized * height;
  };
}

export function buildResidualPlotGeometry(
  joint: JointResidual,
  width: number,
  height: number,
): ResidualPlotGeometry {
  const values = joint.samples.map((sample) => Math.abs(sample.valueNm));
  const peak = values.length > 0 ? Math.max(...values) : 0;
  const yMax = Math.max(joint.thresholdNm, peak) * DEFAULT_HEADROOM;
  const yForValue = makeYScale(height, yMax);

  const count = joint.samples.length;
  const xForIndex = (index: number) => (count <= 1 ? 0 : (index / (count - 1)) * width);

  const residualPoints = joint.samples
    .map((sample, index) => `${xForIndex(index)},${yForValue(sample.valueNm)}`)
    .join(" ");

  const breachPoints: PlotPoint[] = [];
  for (let index = 0; index < joint.samples.length; index += 1) {
    const sample = joint.samples[index];
    if (Math.abs(sample.valueNm) > joint.thresholdNm) {
      breachPoints.push({ x: xForIndex(index), y: yForValue(sample.valueNm) });
    }
  }

  return {
    width,
    height,
    residualPoints,
    thresholdY: yForValue(joint.thresholdNm),
    negThresholdY: yForValue(-joint.thresholdNm),
    zeroY: yForValue(0),
    breachPoints,
    breached: breachPoints.length > 0,
  };
}
