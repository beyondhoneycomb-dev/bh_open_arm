// CG-G-02g: the absence of link7 from collisions.yaml surfaces as a collision-mode
// gap, rather than the link being drawn as if it were covered.

import { describe, expect, it } from "vitest";

import { collisionCoverage, hasCollisionGaps } from "./collisionModel";

const URDF_LINKS = ["link1", "link2", "link3", "link4", "link5", "link6", "link7"];

describe("CG-G-02g collision coverage", () => {
  it("reports link7 as missing when collisions.yaml omits it", () => {
    const declared = URDF_LINKS.filter((link) => link !== "link7");
    const coverage = collisionCoverage(URDF_LINKS, declared);
    expect(coverage.missing).toEqual(["link7"]);
    expect(hasCollisionGaps(coverage)).toBe(true);
  });

  it("reports no gap when every URDF link carries a collision geom", () => {
    const coverage = collisionCoverage(URDF_LINKS, URDF_LINKS);
    expect(coverage.missing).toEqual([]);
    expect(hasCollisionGaps(coverage)).toBe(false);
  });
});
