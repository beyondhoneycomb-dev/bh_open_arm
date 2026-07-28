// CG-G-S12c (render half): the residual series and its threshold line render
// inside the SAME plot element. Splitting them across two plots would hide a
// threshold breach, so every residual plot must contain both series.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  EFFORT_LIMIT_READOUT_LABEL,
  RESIDUAL_COMPARISON_NOTICE,
  THRESHOLD_READOUT_LABEL,
} from "./constants";
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

// Samples well inside the threshold band, so the component's own breach marker
// stays absent and "calm" is never re-derived by the assertions.
function calmJoints(count: number): JointResidual[] {
  return Array.from({ length: count }, (_, index) => ({
    jointName: `openarm_left_joint${index + 1}`,
    samples: [0, 0.2, -0.1].map((valueNm, sampleIndex) => ({
      tMonoMs: sampleIndex * 20,
      valueNm,
    })),
    thresholdNm: 4,
    effortLimitNm: 40,
  }));
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

describe("NORM-009: the threshold UI names the residual as the comparison target", () => {
  it("states the comparison target even when no joint breaches", () => {
    const { container } = render(<ResidualPlot residuals={calmJoints(3)} />);
    expect(container.querySelectorAll('[data-series="breach"]')).toHaveLength(0);
    expect(screen.getByText(RESIDUAL_COMPARISON_NOTICE)).toBeTruthy();
  });

  it("states it once for the panel, not once per joint", () => {
    const { container } = render(<ResidualPlot residuals={calmJoints(3)} />);
    // The plot count is asserted too: on a one-joint fixture "exactly one notice"
    // would pass whether the notice is per-panel or per-joint.
    expect(container.querySelectorAll('[data-plot="residual"]')).toHaveLength(3);
    expect(screen.getAllByText(RESIDUAL_COMPARISON_NOTICE)).toHaveLength(1);
  });

  it("labels the threshold number as the residual threshold, and disowns the effort limit", () => {
    const fixture = calmJoints(1);
    const { container } = render(<ResidualPlot residuals={fixture} />);
    const readout = container.querySelector('[data-readout="threshold"]');
    expect(readout).not.toBeNull();
    // Composed from the exported labels and the values passed IN, so a JSX
    // whitespace slip that glues a label onto its number fails here rather than
    // shipping a readout that reads as one ratio again.
    expect(readout?.textContent).toBe(
      `${THRESHOLD_READOUT_LABEL} ±${fixture[0].thresholdNm} Nm · ` +
        `${EFFORT_LIMIT_READOUT_LABEL} ${fixture[0].effortLimitNm} Nm`,
    );
  });

  it("adds the standing notice without displacing the breach note", () => {
    const { container } = render(<ResidualPlot residuals={joints()} />);
    // The breach-conditional half is asserted first: it must be green both before
    // and after the standing notice lands, or the notice replaced live state
    // instead of joining it.
    expect(container.querySelector('[data-series="breach"]')).not.toBeNull();
    expect(screen.getByText(/임계 초과/)).toBeTruthy();
    expect(screen.getByText(RESIDUAL_COMPARISON_NOTICE)).toBeTruthy();
  });
});
