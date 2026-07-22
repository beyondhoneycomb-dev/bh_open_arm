// Unit gates for the SIM-domain facade projections: the six-check identity and
// ordering (FR-SIM-030), the stiff-gain twin/dry-run precondition (FR-SIM-028b),
// the all-pass real-send predicate (FR-SIM-033), the reconnect-free target swap
// (FR-SIM-097), the MJCF sim-asset basis (FR-SIM-007), and the distinct ghost
// layers (CG-G-S09e).

import { describe, expect, it } from "vitest";

import {
  DRY_RUN_CHECKS,
  DRY_RUN_CHECK_COUNT,
  GHOST_LAYER_STYLES,
  MJCF_ASSET_FACTS,
  TWIN_DRYRUN_REQUIRED_GAIN_PROFILE,
  allChecksPassed,
  ghostLayersAreDistinct,
  noMjcfFactIsHardwareSpec,
  orderedCheckResults,
  swapTarget,
  twinDryRunAllowed,
  type DryRunReport,
} from "./simDomain";

describe("dry-run six checks (FR-SIM-030)", () => {
  it("names exactly the six frozen checks in order", () => {
    expect(DRY_RUN_CHECK_COUNT).toBe(6);
    expect(DRY_RUN_CHECKS.map((meta) => meta.id)).toEqual([
      "position",
      "velocity",
      "torque",
      "cellCollision",
      "selfCollision",
      "lifter",
    ]);
  });

  it("orders a report by the frozen sequence and fills omissions as not_run", () => {
    const report: DryRunReport = {
      checks: [{ id: "lifter", status: "pass" }],
    };
    const ordered = orderedCheckResults(report);
    expect(ordered.map((result) => result.id)).toEqual(DRY_RUN_CHECKS.map((meta) => meta.id));
    expect(ordered.find((result) => result.id === "position")?.status).toBe("not_run");
    expect(ordered.find((result) => result.id === "lifter")?.status).toBe("pass");
  });
});

describe("real-send predicate (FR-SIM-033, CG-G-S09d)", () => {
  it("passes only when all six checks pass", () => {
    const allPass: DryRunReport = {
      checks: DRY_RUN_CHECKS.map((meta) => ({ id: meta.id, status: "pass" as const })),
    };
    expect(allChecksPassed(allPass)).toBe(true);
  });

  it("fails when any check is missing, failed, or not run", () => {
    expect(allChecksPassed(null)).toBe(false);
    const oneFail: DryRunReport = {
      checks: DRY_RUN_CHECKS.map((meta, index) => ({
        id: meta.id,
        status: index === 2 ? ("fail" as const) : ("pass" as const),
      })),
    };
    expect(allChecksPassed(oneFail)).toBe(false);
    const oneMissing: DryRunReport = {
      checks: DRY_RUN_CHECKS.slice(1).map((meta) => ({ id: meta.id, status: "pass" as const })),
    };
    expect(allChecksPassed(oneMissing)).toBe(false);
  });
});

describe("gain parity precondition (FR-SIM-028b, CG-G-S09b)", () => {
  it("requires the stiff profile for twin/dry-run", () => {
    expect(TWIN_DRYRUN_REQUIRED_GAIN_PROFILE).toBe("stiff");
    expect(twinDryRunAllowed("stiff")).toBe(true);
    expect(twinDryRunAllowed("compliant")).toBe(false);
  });
});

describe("sim<->real swap (FR-SIM-097, CG-G-S09c)", () => {
  it("is a pure object swap with no other state", () => {
    expect(swapTarget("sim")).toBe("real");
    expect(swapTarget("real")).toBe("sim");
  });
});

describe("MJCF asset basis (FR-SIM-007, CG-G-S09a)", () => {
  it("holds every MJCF fact as sim-asset-only, never a hardware spec", () => {
    expect(MJCF_ASSET_FACTS.length).toBeGreaterThan(0);
    expect(noMjcfFactIsHardwareSpec()).toBe(true);
    for (const fact of MJCF_ASSET_FACTS) {
      expect(fact.basis).toBe("sim-asset-only");
    }
  });
});

describe("ghost overlay layers (CG-G-S09e)", () => {
  it("differ on every visual dimension", () => {
    expect(ghostLayersAreDistinct()).toBe(true);
    expect(GHOST_LAYER_STYLES.sim.colorToken).not.toBe(GHOST_LAYER_STYLES.real.colorToken);
    expect(GHOST_LAYER_STYLES.sim.opacity).not.toBe(GHOST_LAYER_STYLES.real.opacity);
    expect(GHOST_LAYER_STYLES.sim.outline).not.toBe(GHOST_LAYER_STYLES.real.outline);
  });
});
