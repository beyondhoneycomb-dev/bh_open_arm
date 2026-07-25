// CG-5-04a — route inventory: every 13 §2.6 row has its route AND there are zero
// excess routes and zero invented screens. The audit diffs three committed facts
// against the SCREEN_INVENTORY canon: the frozen route registry (src/routes), the
// route paths it mounts, and the screen directories that exist on disk. A screen the
// spec does not list, an extra route, or a path set that disagrees is a finding — the
// proof that the build "invented no screen" (02c §4.4 negative branch).

import type { AuditViolation } from "./types";
import { VIEWPORT_ROUTE, type ScreenInventoryRow } from "./screenInventory";

// The shape of one registry screen descriptor the audit consumes. It matches
// src/routes/registry.ts ScreenDescriptor structurally without importing its exact
// type, so the diff reads the committed registry as data, not as its own definition.
export interface RegistryScreen {
  id: string;
  paths: readonly string[];
}

function sortedPaths(paths: readonly string[]): string {
  return [...paths].sort().join(",");
}

// Diff the committed route registry against the §2.6 canon.
export function auditRouteInventory(
  canon: readonly ScreenInventoryRow[],
  registryScreens: readonly RegistryScreen[],
  registryRoutePaths: readonly string[],
): AuditViolation[] {
  const violations: AuditViolation[] = [];
  const canonById = new Map(canon.map((row) => [row.id, row]));
  const registryById = new Map(registryScreens.map((screen) => [screen.id, screen]));

  for (const row of canon) {
    const screen = registryById.get(row.id);
    if (!screen) {
      violations.push({
        check: "CG-5-04a",
        where: row.id,
        detail: "§2.6 screen has no route in the committed registry",
      });
      continue;
    }
    if (sortedPaths(screen.paths) !== sortedPaths(row.paths)) {
      violations.push({
        check: "CG-5-04a",
        where: row.id,
        detail: `route paths [${[...screen.paths].sort().join(", ")}] != §2.6 [${[...row.paths].sort().join(", ")}]`,
      });
    }
  }

  for (const screen of registryScreens) {
    if (!canonById.has(screen.id)) {
      violations.push({
        check: "CG-5-04a",
        where: screen.id,
        detail: "registry declares a screen not in 13 §2.6 (invented screen)",
      });
    }
  }

  const canonPathSet = new Set(canon.flatMap((row) => [...row.paths]));
  for (const path of registryRoutePaths) {
    if (path === VIEWPORT_ROUTE) {
      continue; // the one permitted extra route (FR-GUI-003)
    }
    if (!canonPathSet.has(path)) {
      violations.push({
        check: "CG-5-04a",
        where: path,
        detail: "route path not in 13 §2.6 (excess route)",
      });
    }
  }

  if (!registryRoutePaths.includes(VIEWPORT_ROUTE)) {
    violations.push({
      check: "CG-5-04a",
      where: VIEWPORT_ROUTE,
      detail: "shared viewport route missing (FR-GUI-003)",
    });
  }

  return violations;
}

// Diff the committed screen directories against the canon ids: an extra directory is
// an invented screen, a missing one is an unbuilt screen.
export function auditScreenDirectories(
  canonIds: readonly string[],
  screenDirIds: readonly string[],
): AuditViolation[] {
  const violations: AuditViolation[] = [];
  const canonSet = new Set(canonIds);
  const dirSet = new Set(screenDirIds);

  for (const dirId of screenDirIds) {
    if (!canonSet.has(dirId)) {
      violations.push({
        check: "CG-5-04a",
        where: dirId,
        detail: "screen directory not in 13 §2.6 (invented screen)",
      });
    }
  }
  for (const canonId of canonIds) {
    if (!dirSet.has(canonId)) {
      violations.push({
        check: "CG-5-04a",
        where: canonId,
        detail: "§2.6 screen has no screen directory",
      });
    }
  }
  return violations;
}
