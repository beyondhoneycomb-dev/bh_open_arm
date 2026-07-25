// CG-5-04b — each screen's 3D-viewport embed permission matches the §2.6 "3D
// viewport" column. Two directions are findings:
//   - a "none"-tier screen (S-10, S-13) that embeds the shared viewport at all, and
//   - a "read_only"-tier screen that wires the viewport as a command surface.
// An interactive-tier screen may embed with any permission; a read_only-tier screen
// not embedding is a completeness gap, not a permission violation (FR-GUI-003 leaves
// the embed optional), so it is not reported here.
//
// The structural backstop is that the shared viewport component is read-only by
// construction (it renders from a source prop and emits no command / open / re-open):
// that guarantee is proven by scanning the viewport subtree in the test, which bounds
// every embed to at most read-only regardless of the embedding screen.

import type { AuditViolation, ScannedSource } from "./types";
import type { ScreenInventoryRow } from "./screenInventory";

// What a screen's sources reveal about its use of the shared viewport.
export interface EmbedObservation {
  screenId: string;
  embedsViewport: boolean;
  // True when a command-capable prop is wired onto the viewport element, which would
  // turn a read-only embed into a command surface.
  wiresCommandProp: boolean;
}

const VIEWPORT_IMPORT = /from\s+["'][^"']*\/viewport["']/;
const VIEWPORT_ELEMENT = /<Viewport(?:Panel|Canvas)\b/;
// Command-capable props on the viewport element: a handler or an interactivity flag.
const COMMAND_PROP =
  /<Viewport(?:Panel|Canvas)\b[^>]*\b(?:onCommand|commandSink|onJog|onDrag|onJoint|onTarget|interactive|editable)\b/;

// Read a screen's sources into an embed observation. Import AND element are both
// required so a stray mention in a type-only import is not counted as an embed.
export function detectViewportEmbed(
  screenId: string,
  sources: readonly ScannedSource[],
): EmbedObservation {
  let embeds = false;
  let wiresCommand = false;
  for (const source of sources) {
    if (VIEWPORT_IMPORT.test(source.code) && VIEWPORT_ELEMENT.test(source.code)) {
      embeds = true;
    }
    if (COMMAND_PROP.test(source.code)) {
      wiresCommand = true;
    }
  }
  return { screenId, embedsViewport: embeds, wiresCommandProp: wiresCommand };
}

export function auditViewportPermission(
  canon: readonly ScreenInventoryRow[],
  observations: readonly EmbedObservation[],
): AuditViolation[] {
  const violations: AuditViolation[] = [];
  const canonById = new Map(canon.map((row) => [row.id, row]));

  for (const observation of observations) {
    const row = canonById.get(observation.screenId);
    if (!row) {
      violations.push({
        check: "CG-5-04b",
        where: observation.screenId,
        detail: "embed observation for a screen not in 13 §2.6",
      });
      continue;
    }
    if (row.tier === "none" && observation.embedsViewport) {
      violations.push({
        check: "CG-5-04b",
        where: observation.screenId,
        detail: `§2.6 grants no viewport ("${row.viewportCell}") but the screen embeds one`,
      });
    }
    if (row.tier === "read_only" && observation.wiresCommandProp) {
      violations.push({
        check: "CG-5-04b",
        where: observation.screenId,
        detail: `§2.6 grants a read-only viewport ("${row.viewportCell}") but the screen wires it as a command surface`,
      });
    }
  }
  return violations;
}
