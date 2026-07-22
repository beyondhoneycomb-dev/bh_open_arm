// CG-G-02b: a v1 asset URDF is load-blocked and its provenance is recorded.

import { describe, expect, it } from "vitest";

import { evaluateAsset, type AssetProvenance } from "./provenance";

const V1: AssetProvenance = {
  source_repo: "openarm_description",
  commit_sha: "0000000000000000000000000000000000000001",
  robot_version: "1.0",
};

const V2: AssetProvenance = {
  source_repo: "openarm_description",
  commit_sha: "00000000000000000000000000000000000000a2",
  robot_version: "2.0",
};

describe("CG-G-02b asset version gate", () => {
  it("blocks a v1 asset against a v2 accept value and records its provenance", () => {
    const decision = evaluateAsset(V1, "2.0");
    expect(decision.blocked).toBe(true);
    expect(decision.provenance).toEqual(V1);
    expect(decision.reason).toContain("1.0");
    expect(decision.reason).toContain("2.0");
  });

  it("admits an asset whose robot_version matches the backend-accepted version", () => {
    const decision = evaluateAsset(V2, "2.0");
    expect(decision.blocked).toBe(false);
    expect(decision.reason).toBeNull();
    expect(decision.provenance).toEqual(V2);
  });

  it("records provenance even when the asset is admitted", () => {
    const decision = evaluateAsset(V2, "2.0");
    expect(decision.provenance.commit_sha).toBe(V2.commit_sha);
  });
});
