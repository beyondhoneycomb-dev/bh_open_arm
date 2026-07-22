// CG-G-00d: a malformed config subobject defaults on its own; every other
// subobject is preserved verbatim.

import { describe, expect, it } from "vitest";

import { defaultConfig, parseConfig } from "./schema";

describe("CG-G-00d config blast-radius isolation", () => {
  it("keeps valid subobjects and defaults only the malformed one", () => {
    const raw = {
      layout: { sidebarCollapsed: true, density: "compact" },
      theme: { mode: "not-a-mode" }, // malformed
      presets: { viewPresets: { manual: { camera: "wrist" } } },
    };

    const { config, defaulted } = parseConfig(raw);

    expect(defaulted).toEqual(["theme"]);
    // The malformed subobject fell back to its default...
    expect(config.theme).toEqual({ mode: "system" });
    // ...and the untouched ones survived exactly.
    expect(config.layout).toEqual({ sidebarCollapsed: true, density: "compact" });
    expect(config.presets).toEqual({ viewPresets: { manual: { camera: "wrist" } } });
  });

  it("defaults independently when two subobjects are malformed", () => {
    const raw = {
      layout: 42, // malformed
      theme: { mode: "dark" },
      presets: null, // malformed
    };

    const { config, defaulted } = parseConfig(raw);

    expect(new Set(defaulted)).toEqual(new Set(["layout", "presets"]));
    expect(config.theme).toEqual({ mode: "dark" });
    expect(config.layout).toEqual(defaultConfig().layout);
    expect(config.presets).toEqual(defaultConfig().presets);
  });

  it("drops unknown top-level fields (extra=forbid mirror)", () => {
    const { config } = parseConfig({
      theme: { mode: "light" },
      bogus: { anything: 1 },
    });
    expect(config).not.toHaveProperty("bogus");
    expect(config.theme).toEqual({ mode: "light" });
  });

  it("returns all defaults for a non-object document without throwing", () => {
    expect(parseConfig(null).config).toEqual(defaultConfig());
    expect(parseConfig("nope").config).toEqual(defaultConfig());
  });
});
