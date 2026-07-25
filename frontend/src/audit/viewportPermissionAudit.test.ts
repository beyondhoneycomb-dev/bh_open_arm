// CG-5-04b — each screen's 3D-viewport embed permission matches the §2.6 column.
// Real tree: the observed embed of every committed screen agrees with its §2.6 tier,
// and the shared viewport component is read-only by construction (emits no command,
// opens/re-opens no session). Synthetic: a none-tier screen that embeds, a read-only
// screen that wires a command prop, and a viewport source that emits a command all
// make the audit fire. The forbidden-token patterns for the read-only-by-construction
// scan live in this test file so no shipped module carries them (codebase convention).

import { describe, expect, it } from "vitest";

import { scanForPatterns } from "./scan";
import { SCREEN_INVENTORY } from "./screenInventory";
import {
  auditViewportPermission,
  detectViewportEmbed,
  type EmbedObservation,
} from "./viewportPermissionAudit";
import type { NamedPattern } from "./types";
import { screenSubtreeSources, viewportSubtreeSources } from "./testSupport/collect";

// The shared viewport must not command, open or re-open the backend session. These
// carry the forbidden tokens, so they stay in the test file.
const READONLY_BY_CONSTRUCTION: NamedPattern[] = [
  { label: "command emission", pattern: /commandSink|\.send\s*\(/ },
  { label: "session open/re-open", pattern: /\b(?:dis)?connect\s*\(/ },
  { label: "reconnect affordance", pattern: /reconnect/i },
];

function observeCommittedScreens(): EmbedObservation[] {
  return SCREEN_INVENTORY.map((row) =>
    detectViewportEmbed(row.id, screenSubtreeSources(row.id)),
  );
}

describe("CG-5-04b viewport embed permission == 13 §2.6", () => {
  it("every committed screen's embed agrees with its §2.6 tier", () => {
    expect(auditViewportPermission(SCREEN_INVENTORY, observeCommittedScreens())).toEqual([]);
  });

  it("the shared viewport is read-only by construction (no command/open/reconnect)", () => {
    expect(scanForPatterns(viewportSubtreeSources(), READONLY_BY_CONSTRUCTION, "CG-5-04b")).toEqual(
      [],
    );
  });

  it("fires when a none-tier screen (S-10/S-13) embeds the viewport", () => {
    const observation: EmbedObservation = {
      screenId: "S-10",
      embedsViewport: true,
      wiresCommandProp: false,
    };
    const findings = auditViewportPermission(SCREEN_INVENTORY, [observation]);
    expect(findings.some((f) => f.where === "S-10")).toBe(true);
  });

  it("fires when a read-only-tier screen wires the viewport as a command surface", () => {
    const observation: EmbedObservation = {
      screenId: "S-01",
      embedsViewport: true,
      wiresCommandProp: true,
    };
    const findings = auditViewportPermission(SCREEN_INVENTORY, [observation]);
    expect(findings.some((f) => f.where === "S-01")).toBe(true);
  });

  it("does not fault an interactive-tier screen for embedding", () => {
    const observation: EmbedObservation = {
      screenId: "S-04",
      embedsViewport: true,
      wiresCommandProp: true,
    };
    expect(auditViewportPermission(SCREEN_INVENTORY, [observation])).toEqual([]);
  });

  it("detectViewportEmbed reads import+element as an embed and a command prop as such", () => {
    const embed = detectViewportEmbed("S-04", [
      { path: "a.tsx", code: 'import { ViewportPanel } from "../../viewport";\n<ViewportPanel source={s} />' },
    ]);
    expect(embed.embedsViewport).toBe(true);
    expect(embed.wiresCommandProp).toBe(false);

    const wired = detectViewportEmbed("S-04", [
      { path: "b.tsx", code: 'import { ViewportPanel } from "../../viewport";\n<ViewportPanel onCommand={c} />' },
    ]);
    expect(wired.wiresCommandProp).toBe(true);

    const none = detectViewportEmbed("S-13", [{ path: "c.tsx", code: "export const x = 1;" }]);
    expect(none.embedsViewport).toBe(false);
  });

  it("fires when a viewport source emits a command", () => {
    const findings = scanForPatterns(
      [{ path: "fake/ViewportPanel.tsx", code: "commandSink.send(cmd);" }],
      READONLY_BY_CONSTRUCTION,
      "CG-5-04b",
    );
    expect(findings.length).toBeGreaterThan(0);
  });
});
