// CG-G-00b: the route set is exactly 13 §2.6 plus /viewport, diff zero — the
// shell adds or removes no screen. CG-G-00c: every screen resolves its own
// domain-spec query. The expected inventory below is transcribed straight from
// 13 §2.6 and is the ground truth this registry is diffed against.

import { describe, expect, it } from "vitest";

import { allRoutePaths, domainSpecsForScreen, SCREENS, screenPaths, VIEWPORT_PATH } from "./registry";
import type { DomainCode } from "../config/domainSpec";
import type { ScreenId } from "./registry";

// 13 §2.6, S-01..S-13 in order. S-02 carries two routes; the rest one each.
const EXPECTED: ReadonlyArray<{ id: ScreenId; paths: string[]; domains: DomainCode[] }> = [
  { id: "S-01", paths: ["/"], domains: ["SYS", "OPS", "NFR"] },
  { id: "S-02", paths: ["/connection", "/home-zero"], domains: ["CON"] },
  { id: "S-03", paths: ["/motors"], domains: ["MOT"] },
  { id: "S-04", paths: ["/manual"], domains: ["MAN"] },
  { id: "S-05", paths: ["/teleop"], domains: ["TEL"] },
  { id: "S-06", paths: ["/cameras"], domains: ["CAM"] },
  { id: "S-07", paths: ["/collect"], domains: ["REC"] },
  { id: "S-08", paths: ["/datasets"], domains: ["DAT"] },
  { id: "S-09", paths: ["/sim"], domains: ["SIM"] },
  { id: "S-10", paths: ["/training"], domains: ["TRN"] },
  { id: "S-11", paths: ["/inference"], domains: ["INF"] },
  { id: "S-12", paths: ["/safety"], domains: ["SAF"] },
  { id: "S-13", paths: ["/system"], domains: ["OPS"] },
];

describe("CG-G-00b route inventory == 13 §2.6 + /viewport", () => {
  it("has exactly 13 screens in inventory order", () => {
    expect(SCREENS.map((s) => s.id)).toEqual(EXPECTED.map((e) => e.id));
  });

  it("assigns each screen exactly the 13 §2.6 route paths", () => {
    for (const expected of EXPECTED) {
      const screen = SCREENS.find((s) => s.id === expected.id);
      expect(screen?.paths).toEqual(expected.paths);
    }
  });

  it("diffs zero against the 13 §2.6 screen-route set", () => {
    const expectedRoutes = EXPECTED.flatMap((e) => e.paths).sort();
    expect([...screenPaths()].sort()).toEqual(expectedRoutes);
  });

  it("adds /viewport and nothing else beyond the screen routes", () => {
    const all = allRoutePaths();
    expect(all).toContain(VIEWPORT_PATH);
    expect(all.length).toBe(screenPaths().length + 1);
  });

  it("has no duplicate route path", () => {
    const all = allRoutePaths();
    expect(new Set(all).size).toBe(all.length);
  });
});

describe("CG-G-00c each screen queries its own domain spec", () => {
  it("resolves a non-empty, addressable domain spec for every screen", () => {
    for (const expected of EXPECTED) {
      const specs = domainSpecsForScreen(expected.id);
      expect(specs.map((s) => s.code)).toEqual(expected.domains);
      for (const spec of specs) {
        expect(spec.doc).toMatch(/^\d{2}$/);
        expect(spec.specUrl).toContain(spec.doc);
        expect(spec.title.length).toBeGreaterThan(0);
      }
    }
  });
});
