// The rolling FPS / jitter / drop meter, and CG-G-01e: the instrumented target
// count is DERIVED from robot.observation_features, never a hardcoded constant.

import { describe, expect, it } from "vitest";

import { instrumentedChannels, StreamMeter } from "./streamMeter";
import { observationFeatures } from "./synthetic";

describe("CG-G-01e instrument count derived from observation_features", () => {
  it("instruments exactly as many targets as the feature set has, for any set", () => {
    for (const size of [0, 1, 5, 24, 48]) {
      const features = Array.from({ length: size }, (_unused, index) => `feature_${index}`);
      expect(new StreamMeter(instrumentedChannels(features)).instrumentedCount).toBe(size);
    }
  });

  it("follows the live camera configuration — adding a camera adds a target", () => {
    const oneCamera = observationFeatures(["left_wrist"]);
    const threeCameras = observationFeatures(["left_wrist", "right_wrist", "top"]);
    const oneMeter = new StreamMeter(instrumentedChannels(oneCamera));
    const threeMeter = new StreamMeter(instrumentedChannels(threeCameras));
    expect(oneMeter.instrumentedCount).toBe(oneCamera.length);
    expect(threeMeter.instrumentedCount).toBe(threeCameras.length);
    expect(threeMeter.instrumentedCount).toBeGreaterThan(oneMeter.instrumentedCount);
  });
});

describe("StreamMeter FPS / jitter / drop", () => {
  it("reports the frame rate over the rolling window", () => {
    const meter = new StreamMeter(["cam"], 1000);
    const spacing = 1000 / 30;
    for (let index = 0; index < 30; index += 1) {
      meter.mark("cam", index * spacing);
    }
    expect(meter.stats("cam").fps).toBe(30);
    expect(meter.stats("cam").sampleCount).toBe(30);
  });

  it("reports near-zero jitter for even spacing and non-zero for uneven", () => {
    const even = new StreamMeter(["cam"], 10000);
    for (const t of [0, 33, 66, 99]) {
      even.mark("cam", t);
    }
    expect(even.stats("cam").jitterMs).toBeCloseTo(0, 6);

    const uneven = new StreamMeter(["cam"], 10000);
    for (const t of [0, 10, 100]) {
      uneven.mark("cam", t);
    }
    expect(uneven.stats("cam").jitterMs).toBeGreaterThan(0);
  });

  it("drops age out of the rolling window", () => {
    const meter = new StreamMeter(["cam"], 100);
    meter.mark("cam", 0);
    meter.mark("cam", 50);
    meter.mark("cam", 200); // 0 and 50 are now older than 100ms before 200
    expect(meter.stats("cam").sampleCount).toBe(1);
  });

  it("counts drops separately from delivered frames", () => {
    const meter = new StreamMeter(["cam"], 1000);
    meter.mark("cam", 0);
    meter.markDrop("cam");
    meter.markDrop("cam");
    const stats = meter.stats("cam");
    expect(stats.dropCount).toBe(2);
    expect(stats.sampleCount).toBe(1);
  });
});
