// The episode-loop view FSM (WP-G-S07): start -> success/fail/cancel -> reset ->
// repeat. These prove the allowed transitions and, crucially, the command each
// emits — success/fail keep the episode with a verdict, cancel re-records, stop is
// `session_stop` (never a safety stop), and the "repeat" advance carries no command.

import { describe, expect, it } from "vitest";

import { commandForEvent, isAllowed, nextPhase } from "./episodeFsm";

describe("episode FSM transitions", () => {
  it("starts a session only from idle", () => {
    expect(nextPhase("idle", "start")).toBe("recording");
    expect(nextPhase("recording", "start")).toBeNull();
    expect(nextPhase("reset", "start")).toBeNull();
  });

  it("ends the episode with a verdict or cancel only while recording", () => {
    for (const event of ["success", "fail", "cancel"] as const) {
      expect(nextPhase("recording", event)).toBe("reset");
      expect(nextPhase("idle", event)).toBeNull();
      expect(nextPhase("reset", event)).toBeNull();
    }
  });

  it("repeats by advancing from reset back to recording", () => {
    expect(nextPhase("reset", "advance")).toBe("recording");
    expect(nextPhase("recording", "advance")).toBeNull();
  });

  it("stops the session from any active phase", () => {
    expect(nextPhase("recording", "stop")).toBe("idle");
    expect(nextPhase("reset", "stop")).toBe("idle");
    expect(nextPhase("idle", "stop")).toBeNull();
  });

  it("isAllowed mirrors nextPhase", () => {
    expect(isAllowed("idle", "start")).toBe(true);
    expect(isAllowed("idle", "success")).toBe(false);
  });
});

describe("episode FSM command mapping", () => {
  it("start carries the task prompt", () => {
    expect(commandForEvent("start", "pick the cube")).toEqual({
      op: "session_start",
      task: "pick the cube",
    });
  });

  it("success and fail keep the episode with a verdict", () => {
    expect(commandForEvent("success", "t")).toEqual({ op: "episode_end", verdict: "success" });
    expect(commandForEvent("fail", "t")).toEqual({ op: "episode_end", verdict: "fail" });
  });

  it("cancel re-records the current episode", () => {
    expect(commandForEvent("cancel", "t")).toEqual({ op: "episode_rerecord" });
  });

  it("stop is session_stop, not a safety stop", () => {
    expect(commandForEvent("stop", "t")).toEqual({ op: "session_stop" });
  });

  it("advance (repeat) emits no command — the loop already records the next episode", () => {
    expect(commandForEvent("advance", "t")).toBeNull();
  });
});
