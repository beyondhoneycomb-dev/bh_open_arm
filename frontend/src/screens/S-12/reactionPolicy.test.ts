// CG-G-S12a: the default reaction policy is not a hard E-Stop — it is STOP_HOLD.
// On a brakeless arm a power-cut reaction to a collision is a drop, so the safe
// default and the power-cut policy must never be the same value (FR-SAF-037/038).

import { describe, expect, it } from "vitest";

import {
  DEFAULT_REACTION_MODE,
  POWER_CUT_REACTION_MODE,
  REACTION_MODES,
  REACTION_MODE_SPECS,
  isPowerCutReaction,
  reactionDropsLoad,
  resolveSelectedReaction,
} from "./reactionPolicy";

describe("CG-G-S12a: default reaction is STOP_HOLD, never a power cut", () => {
  it("defaults to STOP_HOLD", () => {
    expect(DEFAULT_REACTION_MODE).toBe("STOP_HOLD");
  });

  it("the default is not the power-cut (hard-E-Stop-equivalent) policy", () => {
    expect(isPowerCutReaction(DEFAULT_REACTION_MODE)).toBe(false);
    expect(DEFAULT_REACTION_MODE).not.toBe(POWER_CUT_REACTION_MODE);
  });

  it("the default reaction does not drop the load", () => {
    expect(reactionDropsLoad(DEFAULT_REACTION_MODE)).toBe(false);
    expect(REACTION_MODE_SPECS[DEFAULT_REACTION_MODE].stopCategory).toBe(2);
  });

  it("resolves to STOP_HOLD when the backend has reported no mode", () => {
    expect(resolveSelectedReaction(null)).toBe("STOP_HOLD");
    expect(isPowerCutReaction(resolveSelectedReaction(null))).toBe(false);
  });

  it("carries the six SAF policies with POWER_OFF as the only power cut", () => {
    expect(REACTION_MODES).toEqual([
      "STOP_HOLD",
      "STOP_DECEL",
      "GRAVITY_COMP",
      "RETRACT",
      "ADMITTANCE",
      "POWER_OFF",
    ]);
    const powerCuts = REACTION_MODES.filter(isPowerCutReaction);
    expect(powerCuts).toEqual(["POWER_OFF"]);
  });

  it("marks exactly the load-dropping policies (STOP_DECEL final drop, POWER_OFF)", () => {
    const dropping = REACTION_MODES.filter(reactionDropsLoad);
    expect(dropping).toEqual(["STOP_DECEL", "POWER_OFF"]);
  });
});
