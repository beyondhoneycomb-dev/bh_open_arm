import { describe, expect, it } from "vitest";

import {
  STOP_HOLD,
  TRANSITION_HOLD,
  beginHandoff,
  completeCurrentStep,
  failCurrentStep,
  failPointFor,
  type HandoffState,
} from "./handoff";

function completeAll(state: HandoffState): HandoffState {
  let current = state;
  for (let step = 0; step < 4; step += 1) {
    current = completeCurrentStep(current);
  }
  return current;
}

describe("hand-off FSM (FR-GUI-082, CG-G-04c)", () => {
  it("begins with the four ordered steps, the first active, stream held", () => {
    const state = beginHandoff();
    expect(state.steps.map((step) => step.id)).toEqual([
      "current_owner_halt",
      "stop_hold",
      "new_owner_acquire",
      "first_command_verify",
    ]);
    expect(state.steps[0].status).toBe("active");
    expect(state.steps.slice(1).every((step) => step.status === "pending")).toBe(true);
    expect(state.holdEmission).toBe(TRANSITION_HOLD);
    expect(state.streamContinuous).toBe(true);
  });

  it("advances the active step and holds the stream continuous throughout", () => {
    const state = completeCurrentStep(beginHandoff());
    expect(state.steps[0].status).toBe("done");
    expect(state.steps[1].status).toBe("active");
    expect(state.streamContinuous).toBe(true);
  });

  it("marks every step done when the last completes", () => {
    const done = completeAll(beginHandoff());
    expect(done.steps.every((step) => step.status === "done")).toBe(true);
    expect(done.streamContinuous).toBe(true);
  });

  it("records the fail point on a failed step and degrades to STOP_HOLD without a stream break", () => {
    const failed = failCurrentStep(beginHandoff());
    expect(failed.steps[0].status).toBe("failed");
    expect(failed.steps[0].failure).toBe(failPointFor("current_owner_halt"));
    expect(failed.holdEmission).toBe(STOP_HOLD);
    // The core invariant: a failed hand-off holds the arm, it never releases it.
    expect(failed.streamContinuous).toBe(true);
  });

  it("exposes a fail point for every step so the view can show them all", () => {
    for (const id of [
      "current_owner_halt",
      "stop_hold",
      "new_owner_acquire",
      "first_command_verify",
    ] as const) {
      expect(failPointFor(id).length).toBeGreaterThan(0);
    }
    // @ts-expect-error unknown step id is rejected at the type level too
    expect(() => failPointFor("nope")).toThrow(/unknown hand-off step/);
  });
});
