// CG-5-04f — command-source exclusivity: no UI state where more than one command
// source is simultaneously active. Real tree: the mode catalog assigns each mode
// exactly one send_action holder (IDLE none), and the teleop screen expresses the
// mutual disable of its two candidate sources. Synthetic: a mode listing two holders,
// and a teleop subtree lacking the exclusivity gate, both make the audit fire.

import { describe, expect, it } from "vitest";

import { MODES } from "../mode/modes";
import {
  auditCommandSourceExclusivity,
  modeAuthoritiesFromCatalog,
  teleopExpressesExclusivity,
  type CatalogMode,
} from "./commandSourceAudit";
import { screenSubtreeSources } from "./testSupport/collect";

const catalog = (): CatalogMode[] => MODES.map((mode) => ({ id: mode.id, holder: mode.holder }));

describe("CG-5-04f command-source exclusivity (0 states with >1 source)", () => {
  it("every mode in the committed catalog has at most one command source", () => {
    expect(auditCommandSourceExclusivity(modeAuthoritiesFromCatalog(catalog()))).toEqual([]);
  });

  it("maps the none-holder mode to zero sources, others to exactly one", () => {
    const authorities = modeAuthoritiesFromCatalog(catalog());
    const idle = authorities.find((a) => a.mode === "IDLE");
    const manual = authorities.find((a) => a.mode === "MANUAL");
    expect(idle?.holders).toEqual([]);
    expect(manual?.holders).toEqual(["gui_jog"]);
  });

  it("the teleop screen expresses mutual exclusion of its two candidate sources", () => {
    expect(teleopExpressesExclusivity(screenSubtreeSources("S-05"))).toBe(true);
  });

  it("fires on a mode with two simultaneous command sources", () => {
    const findings = auditCommandSourceExclusivity([
      { mode: "BROKEN", holders: ["gui_jog", "teleoperator"] },
    ]);
    expect(findings.some((f) => f.where === "BROKEN")).toBe(true);
  });

  it("reports a teleop subtree lacking the exclusivity gate as not expressed", () => {
    expect(teleopExpressesExclusivity([{ path: "fake/x.ts", code: "export const x = 1;" }])).toBe(
      false,
    );
  });
});
