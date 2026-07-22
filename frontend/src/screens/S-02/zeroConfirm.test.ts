// CG-G-S02d (unit): the confirm view's per-joint current-vs-rest delta is a pure
// radian subtraction over the URDF joint set, with unknown joints reported rather
// than filled with 0.

import { describe, expect, it } from "vitest";

import { maxAbsDelta, perJointDelta } from "./zeroConfirm";

const JOINTS = ["j1", "j2", "j3"] as const;

describe("CG-G-S02d per-joint delta", () => {
  it("computes current - rest for every joint, in radians", () => {
    const current = { j1: 0.5, j2: -0.25, j3: 1.0 };
    const rest = { j1: 0.0, j2: 0.0, j3: 1.0 };
    const deltas = perJointDelta(current, rest, JOINTS);
    expect(deltas).toEqual([
      { joint: "j1", currentRad: 0.5, restRad: 0.0, deltaRad: 0.5 },
      { joint: "j2", currentRad: -0.25, restRad: 0.0, deltaRad: -0.25 },
      { joint: "j3", currentRad: 1.0, restRad: 1.0, deltaRad: 0.0 },
    ]);
  });

  it("reports an unknown joint as NaN rather than fabricating 0", () => {
    const current = { j1: 0.5, j3: 1.0 };
    const rest = { j1: 0.0, j2: 0.0, j3: 1.0 };
    const deltas = perJointDelta(current, rest, JOINTS);
    expect(Number.isNaN(deltas[1].deltaRad)).toBe(true);
  });

  it("reports the largest absolute delta, or NaN when any joint is unknown", () => {
    const rest = { j1: 0.0, j2: 0.0, j3: 0.0 };
    expect(maxAbsDelta(perJointDelta({ j1: 0.2, j2: -0.6, j3: 0.1 }, rest, JOINTS))).toBeCloseTo(0.6);
    expect(Number.isNaN(maxAbsDelta(perJointDelta({ j1: 0.2 }, rest, JOINTS)))).toBe(true);
  });
});
