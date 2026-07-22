// CG-G-S12c (render half): the residual series and its threshold line render
// inside the SAME plot element. Splitting them across two plots would hide a
// threshold breach, so every residual plot must contain both series.

import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ResidualPlot } from "./ResidualPlot";
import type { JointResidual } from "./residualGeometry";

function joints(): JointResidual[] {
  return [
    {
      jointName: "openarm_left_joint1",
      samples: [0, 1, 6].map((valueNm, index) => ({ tMonoMs: index * 20, valueNm })),
      thresholdNm: 4,
      effortLimitNm: 40,
    },
  ];
}

describe("CG-G-S12c: residual and threshold on the same plot", () => {
  it("renders both the residual series and the threshold line inside one plot", () => {
    const { container } = render(<ResidualPlot residuals={joints()} />);
    const plots = container.querySelectorAll('[data-plot="residual"]');
    expect(plots).toHaveLength(1);
    const plot = plots[0];
    // Both series are children of the SAME plot node.
    expect(plot.querySelector('[data-series="residual"]')).not.toBeNull();
    expect(plot.querySelector('[data-series="threshold"]')).not.toBeNull();
  });

  it("marks the breach on the same plot when the residual exceeds the threshold", () => {
    const { container } = render(<ResidualPlot residuals={joints()} />);
    const plot = container.querySelector('[data-plot="residual"]')!;
    expect(plot.querySelector('[data-series="breach"]')).not.toBeNull();
  });

  it("has no residual view that omits the threshold", () => {
    const { container } = render(<ResidualPlot residuals={joints()} />);
    // Every plot that draws a residual also draws a threshold.
    const plots = Array.from(container.querySelectorAll('[data-plot="residual"]'));
    for (const plot of plots) {
      const hasResidual = plot.querySelector('[data-series="residual"]') !== null;
      const hasThreshold = plot.querySelector('[data-series="threshold"]') !== null;
      expect(hasResidual && hasThreshold).toBe(true);
    }
  });
});
