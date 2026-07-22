import { describe, expect, it } from "vitest";

import {
  PREFLIGHT_ITEM_IDS,
  canStartSession,
  failedPreflightItems,
  preflightIsComplete,
  type PreflightItem,
} from "./preflight";

function allPassing(): PreflightItem[] {
  return PREFLIGHT_ITEM_IDS.map((id) => ({ id, passed: true }));
}

describe("CG-G-03f preflight is a hard gate with no warn-then-proceed", () => {
  it("has exactly the six canonical items", () => {
    expect(PREFLIGHT_ITEM_IDS).toEqual([
      "can",
      "cameras",
      "velocity_torque",
      "calibration",
      "disk",
      "profile",
    ]);
  });

  it("allows start only when the set is complete and every item passes", () => {
    expect(canStartSession(allPassing())).toBe(true);
  });

  it("blocks start when any single item fails", () => {
    for (const failing of PREFLIGHT_ITEM_IDS) {
      const items = allPassing().map((item) =>
        item.id === failing ? { ...item, passed: false } : item,
      );
      expect(canStartSession(items)).toBe(false);
      expect(failedPreflightItems(items).some((f) => f.id === failing)).toBe(true);
    }
  });

  it("treats a missing item as a failure, not a pass by omission", () => {
    const missingProfile = allPassing().filter((item) => item.id !== "profile");
    expect(preflightIsComplete(missingProfile)).toBe(false);
    expect(canStartSession(missingProfile)).toBe(false);
    expect(failedPreflightItems(missingProfile).some((f) => f.id === "profile")).toBe(true);
  });

  it("exposes no override: canStartSession takes only the item list", () => {
    expect(canStartSession.length).toBe(1);
  });
});
