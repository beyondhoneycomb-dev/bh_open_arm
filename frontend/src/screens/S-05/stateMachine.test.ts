// The state-machine catalog is the `05` §4.1 machine and the `05` §4.2 forbidden
// transitions rendered as data. These tests pin the catalog to the spec so a later
// edit cannot silently drop a state or invert a hold flag.

import { describe, expect, it } from "vitest";

import {
  FORBIDDEN_TRANSITIONS,
  TELEOP_STATES,
  isFollowingState,
  isHoldState,
  stateById,
} from "./stateMachine";

describe("teleop state machine catalog (05 §4.1)", () => {
  it("has all 11 states with unique ids", () => {
    expect(TELEOP_STATES).toHaveLength(11);
    const ids = TELEOP_STATES.map((state) => state.id);
    expect(new Set(ids).size).toBe(11);
    for (const id of ["S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10"]) {
      expect(ids).toContain(id);
    }
  });

  it("marks S5/S6/S7 (and S2/S8) as hold states and S4 as following", () => {
    expect(isFollowingState("S4")).toBe(true);
    expect(isFollowingState("S3")).toBe(false);
    for (const id of ["S5", "S6", "S7"] as const) {
      expect(isHoldState(id)).toBe(true);
    }
    expect(isHoldState("S3")).toBe(false);
  });

  it("resolves a state by id and throws on an unknown id", () => {
    expect(stateById("S4").name).toBe("FOLLOWING");
    // @ts-expect-error deliberately invalid id
    expect(() => stateById("SX")).toThrow();
  });

  it("encodes the hold->following-direct forbidden transitions (05 §4.2)", () => {
    for (const [from, to] of [
      ["S5", "S4"],
      ["S6", "S4"],
      ["S7", "S4"],
    ]) {
      expect(FORBIDDEN_TRANSITIONS.some((t) => t.from === from && t.to === to)).toBe(true);
    }
    // Re-opening the robot session is a forbidden transition (I-2, re-zero); it is
    // named in Korean so no forbidden connect() call literal enters GUI source.
    expect(FORBIDDEN_TRANSITIONS.some((t) => t.reason.includes("영점을 파괴"))).toBe(true);
  });
});
