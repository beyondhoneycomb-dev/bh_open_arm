import { describe, expect, it } from "vitest";

import {
  DEPTH_INVALID_COLOR,
  DEPTH_NO_MEASUREMENT_MM,
  depthGridColors,
  depthPixelColor,
  jetColor,
} from "./depthColormap";

describe("depth colormap (CG-G-S06d)", () => {
  it("treats 0 mm as no-measurement, not zero distance", () => {
    expect(DEPTH_NO_MEASUREMENT_MM).toBe(0);
    expect(depthPixelColor(0, 400, 2000)).toBe(DEPTH_INVALID_COLOR);
  });

  it("maps a valid depth through the JET ramp (near = hot, far = cool)", () => {
    const near = depthPixelColor(400, 400, 2000);
    const far = depthPixelColor(2000, 400, 2000);
    expect(near).toMatch(/^rgb\(/);
    expect(far).toMatch(/^rgb\(/);
    expect(near).not.toBe(far);
    // Near end is red-dominant; far end is blue-dominant.
    const nearRgb = near.match(/\d+/g)!.map(Number);
    const farRgb = far.match(/\d+/g)!.map(Number);
    expect(nearRgb[0]).toBeGreaterThan(nearRgb[2]);
    expect(farRgb[2]).toBeGreaterThan(farRgb[0]);
  });

  it("clamps the JET ramp to its endpoints", () => {
    expect(jetColor(-1)).toEqual(jetColor(0));
    expect(jetColor(2)).toEqual(jetColor(1));
  });

  it("colours a whole grid and keeps invalid cells distinct", () => {
    const colors = depthGridColors([400, 800, DEPTH_NO_MEASUREMENT_MM, 2000]);
    expect(colors).toHaveLength(4);
    expect(colors[2]).toBe(DEPTH_INVALID_COLOR);
    expect(colors[0]).not.toBe(colors[3]);
  });
});
