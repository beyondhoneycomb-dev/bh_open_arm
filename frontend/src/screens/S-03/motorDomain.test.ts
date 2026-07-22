// Pure-function proofs for the S-03 acceptance checks that are decidable without a
// DOM: the save guards (CG-G-S03c/d), the reachable-speed clamp (CG-G-S03f), the
// unloaded control block (CG-G-S03e), the seven-code reference (CG-G-S03g) and the
// state-frame parse (CG-G-S03b — parse-only).

import { describe, expect, it } from "vitest";

import {
  MIT_KD_RANGE,
  MIT_KP_RANGE,
  MOT_FAULT_NIBBLES,
  controlAllowed,
  effectiveGripperSpeedRadS,
  gripperSpeedExceedsVMax,
  isFaultNibble,
  limitIsSubset,
  motErrCodeForNibble,
  motErrReference,
  parseMotorStatesFromFrame,
  validateProfileSave,
  type ProfileSaveDraft,
} from "./motorDomain";
import { ERROR_REGISTRY, MECHANICAL_LIMITS_RAD } from "./testSupport/fixtures";

function draft(overrides: Partial<ProfileSaveDraft> = {}): ProfileSaveDraft {
  return {
    name: "test",
    kp: [10, 10, 10, 10, 10, 10, 10, 10],
    kd: [1, 1, 1, 1, 1, 1, 1, 1],
    operationalLimitsRad: MECHANICAL_LIMITS_RAD.map((limit) => ({
      lo: limit.lo + 0.05,
      hi: limit.hi - 0.05,
    })),
    ...overrides,
  };
}

describe("CG-G-S03c: kp∉[0,500] / kd∉[0,5] → save refused", () => {
  it("accepts a draft with gains inside both ranges", () => {
    expect(validateProfileSave(draft(), MECHANICAL_LIMITS_RAD).ok).toBe(true);
  });

  it("refuses when a kp exceeds 500", () => {
    const kp = [600, 10, 10, 10, 10, 10, 10, 10];
    const result = validateProfileSave(draft({ kp }), MECHANICAL_LIMITS_RAD);
    expect(result.ok).toBe(false);
    expect(result.reasons.join(" ")).toMatch(/kp/);
  });

  it("refuses when a kp is negative", () => {
    const kp = [-1, 10, 10, 10, 10, 10, 10, 10];
    expect(validateProfileSave(draft({ kp }), MECHANICAL_LIMITS_RAD).ok).toBe(false);
  });

  it("refuses when a kd exceeds 5", () => {
    const kd = [1, 1, 1, 1, 1, 1, 1, 6];
    const result = validateProfileSave(draft({ kd }), MECHANICAL_LIMITS_RAD);
    expect(result.ok).toBe(false);
    expect(result.reasons.join(" ")).toMatch(/kd/);
  });

  it("pins the ranges to the frozen MIT bounds", () => {
    expect(MIT_KP_RANGE).toEqual({ min: 0, max: 500 });
    expect(MIT_KD_RANGE).toEqual({ min: 0, max: 5 });
  });
});

describe("CG-G-S03d: operational limit ⊄ mechanical → save refused", () => {
  it("passes a strict subset", () => {
    const op = { lo: -1.0, hi: 1.0 };
    const mech = { lo: -1.5, hi: 1.5 };
    expect(limitIsSubset(op, mech)).toBe(true);
  });

  it("rejects a band that widens past the mechanical hard stop", () => {
    const op = { lo: -2.0, hi: 1.0 };
    const mech = { lo: -1.5, hi: 1.5 };
    expect(limitIsSubset(op, mech)).toBe(false);
  });

  it("refuses the whole save when one joint's operational band escapes mechanical", () => {
    const operationalLimitsRad = MECHANICAL_LIMITS_RAD.map((limit) => ({ ...limit }));
    operationalLimitsRad[5] = { lo: -1.5708, hi: 1.5708 }; // J6 mech is ±0.7854
    const result = validateProfileSave(draft({ operationalLimitsRad }), MECHANICAL_LIMITS_RAD);
    expect(result.ok).toBe(false);
    expect(result.reasons.join(" ")).toMatch(/J6/);
  });
});

describe("CG-G-S03f: gripper speed clamped within the motor's vMax", () => {
  it("shows min(configured, vMax) — never the raw configured value", () => {
    // DM4310 vMax is 30; the configured POS_FORCE speed is the misleading 50.
    expect(effectiveGripperSpeedRadS(50, 30)).toBe(30);
  });

  it("does not raise a speed that is already reachable", () => {
    expect(effectiveGripperSpeedRadS(12, 30)).toBe(12);
  });

  it("flags when the configured speed exceeds the motor vMax", () => {
    expect(gripperSpeedExceedsVMax(50, 30)).toBe(true);
    expect(gripperSpeedExceedsVMax(12, 30)).toBe(false);
  });
});

describe("CG-G-S03e: control blocked while no profile is loaded", () => {
  it("blocks control when the active profile is null", () => {
    expect(controlAllowed(null)).toBe(false);
  });

  it("allows control once a profile is loaded", () => {
    expect(controlAllowed("lerobot_follower")).toBe(true);
  });
});

describe("CG-G-S03g: the seven ERR codes map from their nibbles with hints", () => {
  it("maps each fault nibble to its OA-MOT code", () => {
    expect(motErrCodeForNibble("8")).toBe("OA-MOT-008");
    expect(motErrCodeForNibble("A")).toBe("OA-MOT-00A");
    expect(motErrCodeForNibble("E")).toBe("OA-MOT-00E");
  });

  it("returns null for the normal (non-fault) nibbles", () => {
    expect(motErrCodeForNibble("0")).toBeNull();
    expect(motErrCodeForNibble("1")).toBeNull();
    expect(isFaultNibble("1")).toBe(false);
    expect(isFaultNibble("C")).toBe(true);
  });

  it("builds exactly seven reference entries, each with a code and a hint", () => {
    const entries = motErrReference(ERROR_REGISTRY);
    expect(entries).toHaveLength(MOT_FAULT_NIBBLES.length);
    expect(entries).toHaveLength(7);
    for (const entry of entries) {
      expect(entry.code).toMatch(/^OA-MOT-00[89ABCDE]$/);
      // The hint is the registry's own text, not a fabricated fallback.
      expect(entry.recoveryHint).toBe(ERROR_REGISTRY[entry.code].recoveryHint);
      expect(entry.recoveryHint.length).toBeGreaterThan(0);
    }
  });
});

describe("CG-G-S03b: temperatures are parsed from the state frame only", () => {
  it("extracts per-motor temp and err from a state-frame body", () => {
    const body = {
      type: "telemetry",
      motor_states: [
        { joint_name: "J1", temp_mos_c: 41, temp_rotor_c: 38, err_nibble: "1" },
        { joint_name: "J5", temp_mos_c: 52, temp_rotor_c: 49, err_nibble: "B" },
      ],
    };
    const states = parseMotorStatesFromFrame(body);
    expect(states).toHaveLength(2);
    expect(states[1]).toEqual({
      jointName: "J5",
      tempMosC: 52,
      tempRotorC: 49,
      errNibble: "B",
    });
  });

  it("returns nothing when the frame carries no motor_states", () => {
    expect(parseMotorStatesFromFrame({ type: "telemetry" })).toEqual([]);
  });
});
