import { describe, expect, it } from "vitest";

import {
  DEFAULT_SHORTCUTS,
  SHORTCUT_ACTIONS,
  conflictingActions,
  getBinding,
  rebind,
} from "./shortcuts";

describe("shortcut registry (FR-GUI-067)", () => {
  it("covers the minimum action set the spec requires", () => {
    expect(new Set(SHORTCUT_ACTIONS)).toEqual(
      new Set([
        "emergency_stop",
        "soft_stop",
        "episode_start",
        "episode_success",
        "episode_fail",
        "episode_cancel",
        "mode_switch",
        "view_preset",
      ]),
    );
    for (const action of SHORTCUT_ACTIONS) {
      expect(getBinding(DEFAULT_SHORTCUTS, action)).toBeDefined();
    }
  });

  it("has no conflicting default bindings", () => {
    expect(conflictingActions(DEFAULT_SHORTCUTS)).toEqual([]);
  });

  it("rebinds one action without touching the others", () => {
    const next = rebind(DEFAULT_SHORTCUTS, "mode_switch", "Ctrl+M");
    expect(getBinding(next, "mode_switch")?.keys).toBe("Ctrl+M");
    expect(getBinding(next, "emergency_stop")?.keys).toBe(
      getBinding(DEFAULT_SHORTCUTS, "emergency_stop")?.keys,
    );
    // The original mapping is unchanged.
    expect(getBinding(DEFAULT_SHORTCUTS, "mode_switch")?.keys).toBe("M");
  });

  it("detects a chord collision introduced by a rebind", () => {
    const emergency = getBinding(DEFAULT_SHORTCUTS, "emergency_stop")?.keys ?? "Escape";
    const clashed = rebind(DEFAULT_SHORTCUTS, "mode_switch", emergency);
    const conflicts = conflictingActions(clashed);
    expect(conflicts).toContain("emergency_stop");
    expect(conflicts).toContain("mode_switch");
  });
});
