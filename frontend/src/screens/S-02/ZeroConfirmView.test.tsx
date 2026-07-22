// Runtime CG-G-S02d: the confirm view shows the per-joint current-vs-rest delta in
// radians, and reads "no telemetry" rather than fabricating a pose when none is
// present. The embedded viewport takes its WebGL-absent fallback in jsdom.

import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ZeroConfirmView } from "./ZeroConfirmView";

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(() => null);
});
afterEach(() => {
  vi.restoreAllMocks();
});

const JOINTS = ["openarm_left_joint1", "openarm_left_joint2"] as const;

describe("CG-G-S02d confirm view per-joint delta", () => {
  it("renders a delta row per joint with current, rest and Δ in radians", () => {
    const { container } = render(
      <ZeroConfirmView
        jointNames={JOINTS}
        restPositionsRad={{ openarm_left_joint1: 0, openarm_left_joint2: 0 }}
        currentPositionsRad={{ openarm_left_joint1: 0.5, openarm_left_joint2: -0.25 }}
        nowMonoMs={1000}
      />,
    );

    const table = container.querySelector('[data-table="joint-delta"]');
    expect(table).not.toBeNull();

    const row1 = container.querySelector('[data-joint="openarm_left_joint1"]');
    expect(row1?.textContent).toContain("0.5000 rad");
    expect(row1?.querySelector('[data-delta-rad="0.5"]')).not.toBeNull();

    const row2 = container.querySelector('[data-joint="openarm_left_joint2"]');
    expect(row2?.textContent).toContain("-0.2500 rad");
    expect(row2?.querySelector('[data-delta-rad="-0.25"]')).not.toBeNull();
  });

  it("reads 'no telemetry' when the current pose is absent", () => {
    const { container } = render(
      <ZeroConfirmView
        jointNames={JOINTS}
        restPositionsRad={{ openarm_left_joint1: 0, openarm_left_joint2: 0 }}
        currentPositionsRad={null}
        nowMonoMs={1000}
      />,
    );
    expect(container.querySelector('[data-telemetry="none"]')).not.toBeNull();
    expect(container.querySelector('[data-table="joint-delta"]')).toBeNull();
  });
});
