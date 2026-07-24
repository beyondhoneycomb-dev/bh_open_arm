// CG-4A-G1e / CG-G-S10 ⑤ coverage: training cannot clear the gate while a degenerate
// finding is undecided, the preflight is not PASS, the policy is blocked, or VRAM does
// not fit — and it clears once, and only once, all four are resolved. The gate offers
// exactly the three FR-TRN-068 choices.

import { describe, expect, it } from "vitest";

import {
  canStartTraining,
  presentChoices,
  startBlockReasons,
  undecidedFindings,
  type StartGateInput,
} from "./startGate";
import type { DegenerateFinding, PolicyOption, PreflightReport, VramPreflight } from "./types";

const OPEN_POLICY: PolicyOption = {
  capability: {
    id: "unblocked",
    configClass: "TestConfig",
    maxStateDim: 132,
    maxActionDim: 132,
    capSource: "test",
    available: true,
    unavailableReason: null,
  },
  blocked: false,
  blockReason: null,
};

const PASS: PreflightReport = { verdict: "PASS", findings: [] };
const VRAM_OK: VramPreflight = {
  fits: true,
  requiredGb: 10,
  availableGb: 16,
  source: "test",
  alternatives: [],
};

const FINDING: DegenerateFinding = {
  channelName: "right_joint_7.torque",
  joint: "right_joint_7",
  component: ".torque",
  normMode: "MEAN_STD",
  statistic: 3.1e-7,
  threshold: 1e-4,
  amplificationEstimate: 3.2e6,
};

function baseInput(): StartGateInput {
  return { policy: OPEN_POLICY, preflight: PASS, findings: [], decisions: [], vram: VRAM_OK };
}

describe("start gate offers exactly the three FR-TRN-068 choices", () => {
  it("presents EXCLUDE / MANUAL_STATS / PROCEED", () => {
    expect([...presentChoices()]).toEqual(["EXCLUDE", "MANUAL_STATS", "PROCEED"]);
  });
});

describe("start gate blocks until every blocker is resolved (CG-4A-G1e)", () => {
  it("clears with no findings, PASS preflight, open policy, VRAM ok", () => {
    expect(canStartTraining(baseInput())).toBe(true);
    expect(startBlockReasons(baseInput())).toEqual([]);
  });

  it("blocks on an undecided degenerate finding, and names FR-TRN-068", () => {
    const input = { ...baseInput(), findings: [FINDING], decisions: [] };
    expect(canStartTraining(input)).toBe(false);
    expect(undecidedFindings(input.findings, input.decisions)).toHaveLength(1);
    expect(startBlockReasons(input).join(" ")).toContain("FR-TRN-068");
  });

  it("clears once the finding carries any of the three decisions", () => {
    const input = {
      ...baseInput(),
      findings: [FINDING],
      decisions: [{ finding: FINDING, choice: "EXCLUDE" as const, rationale: "irrelevant channel" }],
    };
    expect(undecidedFindings(input.findings, input.decisions)).toHaveLength(0);
    expect(canStartTraining(input)).toBe(true);
  });

  it("blocks on a BLOCK preflight", () => {
    const input = {
      ...baseInput(),
      preflight: {
        verdict: "BLOCK" as const,
        findings: [{ code: "X", channelName: "c", component: null, joint: null, detail: "d" }],
      },
    };
    expect(canStartTraining(input)).toBe(false);
  });

  it("blocks on a blocked policy", () => {
    const blocked: PolicyOption = {
      ...OPEN_POLICY,
      blocked: true,
      blockReason: {
        code: "STATE_DIM_OVER_CAP",
        observed: 48,
        limit: 32,
        source: "configuration_smolvla",
        human: "48 > 32",
      },
    };
    expect(canStartTraining({ ...baseInput(), policy: blocked })).toBe(false);
  });

  it("blocks on insufficient VRAM and shows the source", () => {
    const input = {
      ...baseInput(),
      vram: { fits: false, requiredGb: 22, availableGb: 16, source: "nvidia-smi", alternatives: ["LoRA"] },
    };
    expect(canStartTraining(input)).toBe(false);
    expect(startBlockReasons(input).join(" ")).toContain("nvidia-smi");
  });

  it("blocks when no policy is selected", () => {
    expect(canStartTraining({ ...baseInput(), policy: null })).toBe(false);
  });
});
