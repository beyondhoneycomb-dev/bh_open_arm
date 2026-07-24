// CG-4A-G1a / CG-G-S10a/e/g coverage: the policy list is derived from the registry
// snapshot (not authored), its dimension ceilings are source-derived and carried with
// their source, and the backend's block verdicts (32-cap over 48-dim; vqbet
// unavailable) are surfaced with their reason.

import { describe, expect, it } from "vitest";

import {
  loadPolicyCapabilities,
  resolvePolicyOptions,
  snapshotLerobotVersion,
} from "./policyRegistry";
import type { DatasetOption } from "./types";

const BIMANUAL_48: DatasetOption = {
  repoId: "openarm/test_bimanual",
  revision: "v3.0",
  episodeCount: 100,
  frameCount: 30000,
  stateDim: 48,
  actionDim: 16,
  useVelocityAndTorque: true,
  sizeGb: 10,
};

const POS_ONLY_16: DatasetOption = { ...BIMANUAL_48, stateDim: 16, useVelocityAndTorque: false };

describe("policy registry is runtime-derived (CG-4A-G1a)", () => {
  it("loads a non-empty capability list from the snapshot", () => {
    const caps = loadPolicyCapabilities();
    expect(caps.length).toBeGreaterThan(0);
    for (const cap of caps) {
      expect(cap.id).toBeTruthy();
      expect(cap.capSource).toBeTruthy();
    }
  });

  it("reports the snapshot lerobot version for the provenance line", () => {
    expect(snapshotLerobotVersion()).toMatch(/\d+\.\d+\.\d+/);
  });
});

describe("three-axis block verdicts are surfaced with source (CG-G-S10e)", () => {
  it("blocks a 32-capped policy on a 48-dim dataset and carries the cap source", () => {
    const options = resolvePolicyOptions(loadPolicyCapabilities(), BIMANUAL_48);
    const capped = options.filter(
      (option) => option.capability.maxStateDim === 32,
    );
    expect(capped.length).toBeGreaterThan(0);
    for (const option of capped) {
      expect(option.blocked).toBe(true);
      expect(option.blockReason?.code).toBe("STATE_DIM_OVER_CAP");
      expect(option.blockReason?.observed).toBe(48);
      expect(option.blockReason?.limit).toBe(32);
      // The source is the installed config class, never a copied constant.
      expect(option.blockReason?.source).toContain("configuration_");
    }
  });

  it("allows the same 32-capped policy once the dataset is pos-only 16-dim (third axis is real)", () => {
    const options = resolvePolicyOptions(loadPolicyCapabilities(), POS_ONLY_16);
    const capped = options.filter(
      (option) => option.capability.maxStateDim === 32,
    );
    for (const option of capped) {
      expect(option.blocked).toBe(false);
    }
  });

  it("allows the 132-dim policy on the 48-dim dataset", () => {
    const options = resolvePolicyOptions(loadPolicyCapabilities(), BIMANUAL_48);
    const uncappedByDim = options.filter((option) => option.capability.maxStateDim === 132);
    expect(uncappedByDim.length).toBeGreaterThan(0);
    for (const option of uncappedByDim) {
      expect(option.blocked).toBe(false);
    }
  });

  it("blocks any backend-unavailable policy with its reason regardless of dimension (CG-G-S10g)", () => {
    const options = resolvePolicyOptions(loadPolicyCapabilities(), POS_ONLY_16);
    const unavailable = options.filter((option) => !option.capability.available);
    expect(unavailable.length).toBeGreaterThan(0);
    for (const option of unavailable) {
      expect(option.blocked).toBe(true);
      expect(option.blockReason?.code).toBe("POLICY_UNAVAILABLE");
      expect(option.blockReason?.human).toBeTruthy();
    }
  });
});
