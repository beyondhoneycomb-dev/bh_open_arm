import { describe, expect, it } from "vitest";

import {
  DEFAULT_SHORTCUTS,
  RESERVED_ACTION,
  ReservedShortcutError,
  SHORTCUT_ACTIONS,
  conflictingActions,
  getBinding,
  rebind,
} from "./shortcuts";

describe("shortcut registry (FR-GUI-067)", () => {
  it("covers the minimum action set the spec requires", () => {
    expect(new Set(SHORTCUT_ACTIONS)).toEqual(
      new Set([
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

  // The registry must offer no key for the power cut. §2.7 lists every network edge this
  // system has and none reaches a contactor, so such a key presses nothing — and a stop
  // key that does nothing is read as a stop that works (NORM-007).
  it("offers no POWER_CUT shortcut", () => {
    expect(SHORTCUT_ACTIONS).not.toContain("emergency_stop");
    for (const binding of DEFAULT_SHORTCUTS) {
      expect(binding.label).not.toMatch(/E-Stop|전원/);
    }
  });

  it("has no conflicting default bindings", () => {
    expect(conflictingActions(DEFAULT_SHORTCUTS)).toEqual([]);
  });

  it("rebinds one action without touching the others", () => {
    const next = rebind(DEFAULT_SHORTCUTS, "mode_switch", "Ctrl+M");
    expect(getBinding(next, "mode_switch")?.keys).toBe("Ctrl+M");
    expect(getBinding(next, "view_preset")?.keys).toBe(
      getBinding(DEFAULT_SHORTCUTS, "view_preset")?.keys,
    );
    // The original mapping is unchanged.
    expect(getBinding(DEFAULT_SHORTCUTS, "mode_switch")?.keys).toBe("M");
  });

  // Refused loudly, not silently: a rebind that returned the mapping unchanged would leave
  // the UI showing a chord the registry never accepted.
  it("refuses to rebind the reserved STOP_HOLD key", () => {
    expect(() => rebind(DEFAULT_SHORTCUTS, RESERVED_ACTION, "Ctrl+Q")).toThrow(
      ReservedShortcutError,
    );
    expect(getBinding(DEFAULT_SHORTCUTS, RESERVED_ACTION)?.keys).toBe("Space");
  });

  it("detects a chord collision introduced by a rebind", () => {
    const preset = getBinding(DEFAULT_SHORTCUTS, "view_preset")?.keys ?? "V";
    const clashed = rebind(DEFAULT_SHORTCUTS, "mode_switch", preset);
    const conflicts = conflictingActions(clashed);
    expect(conflicts).toContain("view_preset");
    expect(conflicts).toContain("mode_switch");
  });
});
