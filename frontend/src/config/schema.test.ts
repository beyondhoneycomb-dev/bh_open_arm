// CG-G-00d: a malformed config subobject defaults on its own; every other
// subobject is preserved verbatim.

import { describe, expect, it } from "vitest";

import {
  ARM_SIDES,
  CONTROL_TICK_HZ_DEFAULT,
  DEFAULT_TOOL_ID,
  defaultConfig,
  parseConfig,
} from "./schema";

describe("CG-G-00d config blast-radius isolation", () => {
  it("keeps valid subobjects and defaults only the malformed one", () => {
    const raw = {
      layout: { sidebarCollapsed: true, density: "compact" },
      control: { controlTickHz: 9999 }, // malformed — outside the band
      presets: { viewPresets: { manual: { camera: "wrist" } } },
    };

    const { config, defaulted } = parseConfig(raw);

    expect(defaulted).toEqual(["control"]);
    // The malformed subobject fell back to its default...
    expect(config.control).toEqual({ controlTickHz: CONTROL_TICK_HZ_DEFAULT });
    // ...and the untouched ones survived exactly.
    expect(config.layout).toEqual({ sidebarCollapsed: true, density: "compact" });
    expect(config.presets).toEqual({ viewPresets: { manual: { camera: "wrist" } } });
  });

  it("defaults independently when two subobjects are malformed", () => {
    const raw = {
      layout: 42, // malformed
      control: { controlTickHz: 120 },
      presets: null, // malformed
    };

    const { config, defaulted } = parseConfig(raw);

    expect(new Set(defaulted)).toEqual(new Set(["layout", "presets"]));
    expect(config.control).toEqual({ controlTickHz: 120 });
    expect(config.layout).toEqual(defaultConfig().layout);
    expect(config.presets).toEqual(defaultConfig().presets);
  });

  it("drops unknown top-level fields (extra=forbid mirror)", () => {
    const { config } = parseConfig({
      control: { controlTickHz: 50 },
      bogus: { anything: 1 },
    });
    expect(config).not.toHaveProperty("bogus");
    expect(config.control).toEqual({ controlTickHz: 50 });
  });

  it("returns all defaults for a non-object document without throwing", () => {
    expect(parseConfig(null).config).toEqual(defaultConfig());
    expect(parseConfig("nope").config).toEqual(defaultConfig());
  });
});

describe("endEffector subobject", () => {
  const bothArms = {
    left: { toolId: "gripper", toolMassKg: 0.42 },
    right: { toolId: "fixed_spatula", toolMassKg: null },
  };

  it("round-trips both arms verbatim", () => {
    const { config, defaulted } = parseConfig({ endEffector: bothArms });

    expect(defaulted).toEqual([]);
    expect(config.endEffector).toEqual(bothArms);
  });

  it("defaults both arms to the tool with no gripper motor", () => {
    const { endEffector } = defaultConfig();
    for (const side of ARM_SIDES) {
      expect(endEffector[side]).toEqual({ toolId: DEFAULT_TOOL_ID, toolMassKg: null });
    }
    expect(DEFAULT_TOOL_ID).toBe("fixed_spatula");
  });

  it("defaults only itself when malformed and leaves layout untouched", () => {
    const { config, defaulted } = parseConfig({
      layout: { sidebarCollapsed: true, density: "compact" },
      endEffector: { left: { toolId: "gripper" } }, // no right arm, no mass field
    });

    expect(defaulted).toEqual(["endEffector"]);
    expect(config.endEffector).toEqual(defaultConfig().endEffector);
    expect(config.layout).toEqual({ sidebarCollapsed: true, density: "compact" });
  });

  it("accepts any non-empty toolId — the registry is the backend's, not a list here", () => {
    const laterTool = {
      left: { toolId: "suction_cup_v3", toolMassKg: null },
      right: { toolId: "torque_wrench", toolMassKg: 1.5 },
    };
    const { config, defaulted } = parseConfig({ endEffector: laterTool });

    expect(defaulted).toEqual([]);
    expect(config.endEffector).toEqual(laterTool);
  });

  it("refuses an empty toolId rather than carrying it", () => {
    const { defaulted } = parseConfig({
      endEffector: {
        left: { toolId: "   ", toolMassKg: null },
        right: { toolId: "fixed_spatula", toolMassKg: null },
      },
    });
    expect(defaulted).toEqual(["endEffector"]);
  });

  it("refuses zero, negative and non-finite masses; null is accepted", () => {
    for (const badMass of [0, -1, Number.NaN, Number.POSITIVE_INFINITY, "0.5", undefined]) {
      const { defaulted } = parseConfig({
        endEffector: {
          left: { toolId: "gripper", toolMassKg: badMass },
          right: { toolId: "fixed_spatula", toolMassKg: null },
        },
      });
      expect(defaulted, `mass ${String(badMass)} must be refused`).toEqual(["endEffector"]);
    }

    const { defaulted } = parseConfig({
      endEffector: {
        left: { toolId: "gripper", toolMassKg: null },
        right: { toolId: "fixed_spatula", toolMassKg: null },
      },
    });
    expect(defaulted).toEqual([]);
  });
});
