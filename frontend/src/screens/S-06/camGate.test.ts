import { describe, expect, it } from "vitest";

import {
  PG_CAM_BLOCKED_NOTE,
  PG_CAM_PENDING_NOTE,
  PG_DEPTH_REDUCED_NOTE,
  depthLayerEnabled,
  depthNote,
  tileGate,
  type CameraGateState,
} from "./camGate";

function gates(overrides: Partial<CameraGateState> = {}): CameraGateState {
  return { pgCam001: "pending", pgDepth001: "pending", blockedSlots: [], ...overrides };
}

describe("graceful 3C-gate rendering (PG-CAM-001 / PG-DEPTH-001)", () => {
  it("renders a pending gate as pending, blocking nothing", () => {
    const view = tileGate("front", gates({ pgCam001: "pending" }));
    expect(view.disposition).toBe("pending");
    expect(view.note).toBe(PG_CAM_PENDING_NOTE);
  });

  it("blocks only the degraded config tile on PG-CAM-001 DEGRADED_ACCEPTED", () => {
    const state = gates({ pgCam001: "degraded_accepted", blockedSlots: ["front"] });
    expect(tileGate("front", state).disposition).toBe("blocked");
    expect(tileGate("front", state).note).toBe(PG_CAM_BLOCKED_NOTE);
    expect(tileGate("left_wrist", state).disposition).toBe("normal");
  });

  it("renders a passed gate as normal", () => {
    expect(tileGate("front", gates({ pgCam001: "pass" })).disposition).toBe("normal");
  });

  it("keeps depth on for pending/pass but removes it on a PG-DEPTH-001 failure", () => {
    expect(depthLayerEnabled(gates({ pgDepth001: "pending" }))).toBe(true);
    expect(depthLayerEnabled(gates({ pgDepth001: "pass" }))).toBe(true);
    expect(depthLayerEnabled(gates({ pgDepth001: "fail_blocking" }))).toBe(false);
    expect(depthLayerEnabled(gates({ pgDepth001: "degraded_accepted" }))).toBe(false);
  });

  it("distinguishes a pending depth note from a reduced one", () => {
    expect(depthNote(gates({ pgDepth001: "pass" }))).toBeNull();
    expect(depthNote(gates({ pgDepth001: "fail_blocking" }))).toBe(PG_DEPTH_REDUCED_NOTE);
    expect(depthNote(gates({ pgDepth001: "pending" }))).not.toBeNull();
  });
});
