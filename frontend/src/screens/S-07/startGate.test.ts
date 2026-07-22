// CG-G-S07f / CG-G-S07g predicates. The start gate reuses the WP-G-03 global
// surface: it blocks below the one-hour disk headroom and requires the push_to_hub
// confirm — deciding neither threshold itself.

import { describe, expect, it } from "vitest";

import type { PreflightItem, PushToHubState } from "../../global";
import { needsPushToHubConfirm, startBlocked, storageHeadroomOk } from "./startGate";
import type { StoragePrediction } from "./types";

const ALL_PASS: PreflightItem[] = [
  { id: "can", passed: true },
  { id: "cameras", passed: true },
  { id: "velocity_torque", passed: true },
  { id: "calibration", passed: true },
  { id: "disk", passed: true },
  { id: "profile", passed: true },
];

function storage(headroomHours: number): StoragePrediction {
  return { freeBytes: 1, totalBytes: 2, bytesPerHour: 1, headroomHours };
}

describe("storage headroom (CG-G-S07g)", () => {
  it("is ok at or above one hour, blocked below", () => {
    expect(storageHeadroomOk(storage(1))).toBe(true);
    expect(storageHeadroomOk(storage(2.5))).toBe(true);
    expect(storageHeadroomOk(storage(0.5))).toBe(false);
  });

  it("blocks the start when headroom is under an hour even if preflight passes", () => {
    expect(startBlocked(ALL_PASS, storage(2))).toBe(false);
    expect(startBlocked(ALL_PASS, storage(0.5))).toBe(true);
  });

  it("blocks the start when the preflight is incomplete or failing", () => {
    expect(startBlocked([{ id: "can", passed: false }], storage(5))).toBe(true);
    expect(startBlocked(ALL_PASS.slice(0, 3), storage(5))).toBe(true); // missing items
  });
});

describe("push_to_hub confirm requirement (CG-G-S07f)", () => {
  const on: PushToHubState = { enabled: true, private: false, tags: [] };
  const off: PushToHubState = { enabled: false, private: true, tags: [] };

  it("requires a confirm only when push_to_hub is on", () => {
    expect(needsPushToHubConfirm(on)).toBe(true);
    expect(needsPushToHubConfirm(off)).toBe(false);
  });
});
