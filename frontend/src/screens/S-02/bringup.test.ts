// CG-G-S02b (unit): the bringup order is frozen and connect_readonly is first,
// with no skip path. These assertions cover the static half of CG-G-S02b (the
// ordered table) and the sequential-advance invariant the runtime half replays.

import { describe, expect, it } from "vitest";

import {
  advanceBringup,
  BRINGUP_STEP_IDS,
  bringupComplete,
  firstBackendAction,
  INITIAL_BRINGUP_PROGRESS,
  nextBringupStepId,
  pendingBringupStep,
  type BringupBackendAction,
  type BringupProgress,
} from "./bringup";

describe("CG-G-S02b bringup order", () => {
  it("names connect_readonly as the first step and first backend action", () => {
    expect(BRINGUP_STEP_IDS[0]).toBe("connect_readonly");
    expect(firstBackendAction()).toBe("connect_readonly");
  });

  it("orders the four steps exactly connect_readonly -> verify -> set_zero -> enable", () => {
    expect([...BRINGUP_STEP_IDS]).toEqual([
      "connect_readonly",
      "verify",
      "set_zero",
      "enable",
    ]);
  });

  it("advances only to the immediate successor — no jump-ahead", () => {
    expect(nextBringupStepId("connect_readonly")).toBe("verify");
    expect(nextBringupStepId("verify")).toBe("set_zero");
    expect(nextBringupStepId("set_zero")).toBe("enable");
    expect(nextBringupStepId("enable")).toBeNull();
  });

  it("emits connect_readonly as the very first backend action at runtime", () => {
    const first = advanceBringup(INITIAL_BRINGUP_PROGRESS);
    expect(first.emitted).toBe("connect_readonly");
    expect(first.completedStep).toBe("connect_readonly");
  });

  it("drives the whole sequence and emits actions in order (verify emits none)", () => {
    let progress: BringupProgress = INITIAL_BRINGUP_PROGRESS;
    const emitted: (BringupBackendAction | null)[] = [];
    for (let step = 0; step < BRINGUP_STEP_IDS.length; step += 1) {
      const result = advanceBringup(progress);
      emitted.push(result.emitted);
      progress = result.progress;
    }
    expect(emitted).toEqual(["connect_readonly", null, "set_zero", "enable_torque"]);
    expect(progress.emittedActions).toEqual(["connect_readonly", "set_zero", "enable_torque"]);
    expect(bringupComplete(progress)).toBe(true);
    expect(pendingBringupStep(progress)).toBeNull();
  });

  it("is a no-op once complete", () => {
    let progress: BringupProgress = INITIAL_BRINGUP_PROGRESS;
    for (let step = 0; step < BRINGUP_STEP_IDS.length; step += 1) {
      progress = advanceBringup(progress).progress;
    }
    const afterEnd = advanceBringup(progress);
    expect(afterEnd.emitted).toBeNull();
    expect(afterEnd.progress).toBe(progress);
  });
});
