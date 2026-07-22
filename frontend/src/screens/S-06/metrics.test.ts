import { describe, expect, it } from "vitest";

import type { StreamStats } from "../../ws/streamMeter";
import { DROP_WARN_FRACTION, FPS_WARN_RATIO, evaluateStream, fpsBelowFloor } from "./metrics";

function stats(fps: number): StreamStats {
  return { channel: "observation.images.front", fps, jitterMs: 1, dropCount: 0, sampleCount: 30 };
}

describe("WARN at <95% of target or >2% drop (CG-G-S06e)", () => {
  it("uses the NFR-CAM-006 / NFR-CAM-003 reference lines", () => {
    expect(FPS_WARN_RATIO).toBe(0.95);
    expect(DROP_WARN_FRACTION).toBe(0.02);
  });

  it("marks a stream WARN when achieved FPS is below 95% of target", () => {
    // 30 × 0.95 = 28.5.
    expect(fpsBelowFloor(28.4, 30)).toBe(true);
    expect(fpsBelowFloor(28.6, 30)).toBe(false);
    expect(evaluateStream(stats(26), 30, 0).level).toBe("warn");
    expect(evaluateStream(stats(29.5), 30, 0).level).toBe("ok");
  });

  it("marks a stream WARN when the record drop fraction exceeds 2%", () => {
    expect(evaluateStream(stats(30), 30, 0.03).level).toBe("warn");
    expect(evaluateStream(stats(30), 30, 0.01).level).toBe("ok");
  });

  it("is UNKNOWN, never a fabricated OK, when the camera has no configured target", () => {
    expect(evaluateStream(stats(30), null, 0).level).toBe("unknown");
  });

  it("carries all three metrics through unchanged", () => {
    const view = evaluateStream(
      { channel: "c", fps: 29.4, jitterMs: 1.6, dropCount: 2, sampleCount: 29 },
      30,
      0.004,
    );
    expect(view.fps).toBe(29.4);
    expect(view.jitterMs).toBe(1.6);
    expect(view.dropCount).toBe(2);
    expect(view.recordDropFraction).toBe(0.004);
  });
});
