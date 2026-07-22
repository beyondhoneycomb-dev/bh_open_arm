// CG-G-S12c (geometry half): the residual and the threshold live on one shared
// y-scale. The proof is that a residual sample equal to the threshold maps to the
// exact y of the threshold line — if they were on separate scales a breach could
// be drawn below the line it actually exceeds. Breach detection uses the backend
// threshold, unchanged.

import { describe, expect, it } from "vitest";

import { buildResidualPlotGeometry, type JointResidual } from "./residualGeometry";

const WIDTH = 360;
const HEIGHT = 96;

function joint(values: number[], thresholdNm: number): JointResidual {
  return {
    jointName: "openarm_left_joint1",
    samples: values.map((valueNm, index) => ({ tMonoMs: index * 20, valueNm })),
    thresholdNm,
    effortLimitNm: 40,
  };
}

describe("CG-G-S12c: residual and threshold share one plot scale", () => {
  it("maps a sample equal to the threshold onto the threshold line", () => {
    const geometry = buildResidualPlotGeometry(joint([4, -4, 4], 4), WIDTH, HEIGHT);
    // First sample value is exactly the threshold; its y must equal thresholdY.
    const firstY = Number(geometry.residualPoints.split(" ")[0].split(",")[1]);
    expect(firstY).toBeCloseTo(geometry.thresholdY, 6);
  });

  it("keeps the threshold line inside the plot box", () => {
    const geometry = buildResidualPlotGeometry(joint([1, -1, 2], 4), WIDTH, HEIGHT);
    expect(geometry.thresholdY).toBeGreaterThanOrEqual(0);
    expect(geometry.thresholdY).toBeLessThanOrEqual(HEIGHT);
    expect(geometry.negThresholdY).toBeGreaterThanOrEqual(0);
    expect(geometry.negThresholdY).toBeLessThanOrEqual(HEIGHT);
    // Symmetric about the zero baseline.
    expect(geometry.zeroY).toBeCloseTo((geometry.thresholdY + geometry.negThresholdY) / 2, 6);
  });

  it("marks a breach when a sample exceeds the backend threshold", () => {
    const geometry = buildResidualPlotGeometry(joint([1, 2, 6.5], 4), WIDTH, HEIGHT);
    expect(geometry.breached).toBe(true);
    expect(geometry.breachPoints).toHaveLength(1);
  });

  it("reports no breach when every sample stays within the threshold", () => {
    const geometry = buildResidualPlotGeometry(joint([1, -1.5, 2], 4), WIDTH, HEIGHT);
    expect(geometry.breached).toBe(false);
    expect(geometry.breachPoints).toEqual([]);
  });
});
