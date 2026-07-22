// CG-G-02d: a partial-joint frame is rejected, not merged. A full snapshot every
// frame is forced; a view can never draw a missing (zero-filled) motor as live.

import { describe, expect, it } from "vitest";

import { acceptSnapshot, type JointFrame } from "./jointSnapshot";

const EXPECTED = ["j1", "j2", "j3"];

function frame(positionsRad: Record<string, number>, frameMonoMs = 1000): JointFrame {
  return { positionsRad, frameMonoMs };
}

describe("CG-G-02d full-joint snapshot gate", () => {
  it("accepts a frame that carries every expected joint", () => {
    const result = acceptSnapshot(frame({ j1: 0.1, j2: 0.2, j3: 0.3 }), EXPECTED);
    expect(result.accepted).toBe(true);
    if (result.accepted) {
      expect(result.positionsRad).toEqual({ j1: 0.1, j2: 0.2, j3: 0.3 });
      expect(result.frameMonoMs).toBe(1000);
    }
  });

  it("rejects a partial-joint frame", () => {
    const result = acceptSnapshot(frame({ j1: 0.1, j2: 0.2 }), EXPECTED);
    expect(result.accepted).toBe(false);
    if (!result.accepted) {
      expect(result.reason).toBe("partial-joint-frame");
      expect(result.missing).toEqual(["j3"]);
    }
  });

  it("rejects a frame with an unexpected joint (no silent merge of extras)", () => {
    const result = acceptSnapshot(frame({ j1: 0.1, j2: 0.2, j3: 0.3, j4: 0.4 }), EXPECTED);
    expect(result.accepted).toBe(false);
    if (!result.accepted) {
      expect(result.reason).toBe("unexpected-joint");
      expect(result.unexpected).toEqual(["j4"]);
    }
  });

  it("rejects a frame with a non-finite value", () => {
    const result = acceptSnapshot(frame({ j1: 0.1, j2: Number.NaN, j3: 0.3 }), EXPECTED);
    expect(result.accepted).toBe(false);
    if (!result.accepted) {
      expect(result.reason).toBe("non-finite-value");
    }
  });

  it("is stateless: a partial frame after a full one is still rejected (0 merge dependency)", () => {
    expect(acceptSnapshot(frame({ j1: 0.1, j2: 0.2, j3: 0.3 }), EXPECTED).accepted).toBe(true);
    expect(acceptSnapshot(frame({ j2: 0.9 }), EXPECTED).accepted).toBe(false);
  });
});
