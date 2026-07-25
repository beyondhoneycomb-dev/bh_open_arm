// The cumulative completion audit (02c §4.4): the single cross-screen pass that runs
// all four §2.6 axes / six gates over the committed 13-screen tree at once and proves
// zero findings. Consistency is the target, so this runs whole — not per screen. It
// builds no screen and edits none. The forbidden-token patterns (reconnect,
// connect()) live here in the test, off the shipped modules, as the codebase requires.

import { describe, expect, it } from "vitest";

import { MODES } from "../mode/modes";
import { SCREENS, allRoutePaths } from "../routes/registry";
import {
  auditCommandSourceExclusivity,
  auditRouteInventory,
  auditScreenDirectories,
  auditViewportPermission,
  canonScreenIds,
  detectViewportEmbed,
  findDisallowedUrls,
  findOffOriginTags,
  modeAuthoritiesFromCatalog,
  scanForPatterns,
  SCREEN_INVENTORY,
  teleopExpressesExclusivity,
  type AuditViolation,
  type NamedPattern,
  type RegistryScreen,
} from "./index";
import {
  readHtml,
  screenDirIds,
  screenSubtreeSources,
  shippedSpaSources,
  viewportSubtreeSources,
} from "./testSupport/collect";

const RECONNECT: NamedPattern[] = [
  { label: "reconnect symbol", pattern: /reconnect/i },
  {
    label: "reconnect button",
    pattern: /<button\b[^>]*>[^<]*(?:재연결|재접속|다시\s*연결)[^<]*<\/button>/,
  },
];
const SESSION_REOPEN: NamedPattern[] = [
  { label: "connect()/disconnect() call", pattern: /\b(?:dis)?connect\s*\(/ },
];

function runCompletionAudit(): Record<string, AuditViolation[]> {
  const registryScreens: RegistryScreen[] = SCREENS.map((s) => ({ id: s.id, paths: s.paths }));
  const shipped = shippedSpaSources();
  const { path: htmlPath, html } = readHtml("index.html");

  const embeds = SCREEN_INVENTORY.map((row) =>
    detectViewportEmbed(row.id, screenSubtreeSources(row.id)),
  );

  return {
    "CG-5-04a": [
      ...auditRouteInventory(SCREEN_INVENTORY, registryScreens, allRoutePaths()),
      ...auditScreenDirectories(canonScreenIds(), screenDirIds()),
    ],
    "CG-5-04b": [
      ...auditViewportPermission(SCREEN_INVENTORY, embeds),
      ...scanForPatterns(
        viewportSubtreeSources(),
        [
          { label: "command emission", pattern: /commandSink|\.send\s*\(/ },
          ...SESSION_REOPEN,
          ...RECONNECT,
        ],
        "CG-5-04b",
      ),
    ],
    "CG-5-04c": [...findDisallowedUrls(shipped), ...findOffOriginTags(htmlPath, html)],
    "CG-5-04d": scanForPatterns(shipped, RECONNECT, "CG-5-04d"),
    "CG-5-04e": scanForPatterns(shipped, SESSION_REOPEN, "CG-5-04e"),
    "CG-5-04f": auditCommandSourceExclusivity(modeAuthoritiesFromCatalog(MODES)),
  };
}

describe("WP-5-04 GUI 13-screen completion audit (cumulative, cross-screen)", () => {
  const report = runCompletionAudit();

  for (const gate of ["CG-5-04a", "CG-5-04b", "CG-5-04c", "CG-5-04d", "CG-5-04e", "CG-5-04f"]) {
    it(`${gate}: zero findings over the committed tree`, () => {
      expect(report[gate]).toEqual([]);
    });
  }

  it("covers all six gates and the teleop exclusivity expression", () => {
    expect(Object.keys(report).sort()).toEqual([
      "CG-5-04a",
      "CG-5-04b",
      "CG-5-04c",
      "CG-5-04d",
      "CG-5-04e",
      "CG-5-04f",
    ]);
    expect(teleopExpressesExclusivity(screenSubtreeSources("S-05"))).toBe(true);
  });

  it("audits exactly the 13 §2.6 screens and invents none", () => {
    expect(SCREEN_INVENTORY.length).toBe(13);
    expect(screenDirIds().length).toBe(13);
  });
});
