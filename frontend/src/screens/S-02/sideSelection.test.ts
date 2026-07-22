// CG-G-S02a (unit): with no side chosen, progress is impossible. The gate is the
// screen's only defence against the backend's silent ±5° lock.

import { describe, expect, it } from "vitest";

import { ARM_SIDES, canProceedWithSide, followerSidesFor } from "./sideSelection";

describe("CG-G-S02a side gate", () => {
  it("refuses progress when no side is chosen", () => {
    expect(canProceedWithSide(null)).toBe(false);
  });

  it("allows progress for every concrete side", () => {
    for (const side of ARM_SIDES) {
      expect(canProceedWithSide(side)).toBe(true);
    }
  });

  it("maps bimanual to both followers and a single side to itself", () => {
    expect(followerSidesFor("bimanual")).toEqual(["left", "right"]);
    expect(followerSidesFor("left")).toEqual(["left"]);
    expect(followerSidesFor("right")).toEqual(["right"]);
  });
});
