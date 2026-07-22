// CG-G-02e: stream age over threshold marks the view stale and blocks all control
// input; recovery is by fresh frames alone (no reconnect anywhere in the path).

import { describe, expect, it } from "vitest";

import { controlInputAllowed, evaluateStreamAge } from "./streamAge";

describe("CG-G-02e stream-age control gate", () => {
  it("treats no-frames-yet as maximally stale and control-blocked", () => {
    const state = evaluateStreamAge(null, 5000);
    expect(state.stale).toBe(true);
    expect(state.controlBlocked).toBe(true);
    expect(controlInputAllowed(state)).toBe(false);
  });

  it("is live and control-allowed within the threshold", () => {
    const state = evaluateStreamAge(1000, 1100, 250);
    expect(state.ageMs).toBe(100);
    expect(state.stale).toBe(false);
    expect(controlInputAllowed(state)).toBe(true);
  });

  it("blocks all control input once age crosses the threshold", () => {
    const state = evaluateStreamAge(1000, 1400, 250);
    expect(state.ageMs).toBe(400);
    expect(state.stale).toBe(true);
    expect(controlInputAllowed(state)).toBe(false);
  });

  it("recovers by a fresh frame — a newer accepted frame unblocks control", () => {
    const stale = evaluateStreamAge(1000, 1400, 250);
    expect(stale.controlBlocked).toBe(true);
    const recovered = evaluateStreamAge(1400, 1450, 250);
    expect(recovered.stale).toBe(false);
    expect(controlInputAllowed(recovered)).toBe(true);
  });
});
