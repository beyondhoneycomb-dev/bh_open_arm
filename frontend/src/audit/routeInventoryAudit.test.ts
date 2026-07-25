// CG-5-04a — every 13 §2.6 row has a route, zero excess routes, zero invented
// screens. Real tree: the committed route registry and the on-disk screen dirs diff
// zero against the §2.6 canon. Synthetic: each fault (invented screen, missing screen,
// path mismatch, excess route, invented/missing directory) makes the audit fire.

import { describe, expect, it } from "vitest";

import { SCREENS, VIEWPORT_PATH, allRoutePaths } from "../routes/registry";
import { SCREEN_INVENTORY, canonScreenIds } from "./screenInventory";
import {
  auditRouteInventory,
  auditScreenDirectories,
  type RegistryScreen,
} from "./routeInventoryAudit";
import { screenDirIds } from "./testSupport/collect";

const registryScreens = (): RegistryScreen[] =>
  SCREENS.map((screen) => ({ id: screen.id, paths: screen.paths }));

describe("CG-5-04a route inventory == 13 §2.6, 0 excess", () => {
  it("committed registry matches the §2.6 canon with zero findings", () => {
    expect(auditRouteInventory(SCREEN_INVENTORY, registryScreens(), allRoutePaths())).toEqual([]);
  });

  it("committed screen directories match the §2.6 canon with zero findings", () => {
    expect(auditScreenDirectories(canonScreenIds(), screenDirIds())).toEqual([]);
  });

  it("mounts the shared /viewport route and only that beyond the 13 screens", () => {
    const nonScreen = allRoutePaths().filter((p) => !SCREEN_INVENTORY.some((r) => r.paths.includes(p)));
    expect(nonScreen).toEqual([VIEWPORT_PATH]);
  });

  it("fires on an invented screen route", () => {
    const invented = [...registryScreens(), { id: "S-99", paths: ["/ghost"] }];
    const paths = [...allRoutePaths(), "/ghost"];
    const findings = auditRouteInventory(SCREEN_INVENTORY, invented, paths);
    expect(findings.some((f) => f.where === "S-99")).toBe(true);
    expect(findings.some((f) => f.where === "/ghost")).toBe(true);
  });

  it("fires on a missing §2.6 screen", () => {
    const missing = registryScreens().filter((s) => s.id !== "S-07");
    const paths = allRoutePaths().filter((p) => p !== "/collect");
    const findings = auditRouteInventory(SCREEN_INVENTORY, missing, paths);
    expect(findings.some((f) => f.where === "S-07")).toBe(true);
  });

  it("fires on a route path set that disagrees with §2.6", () => {
    const mutated = registryScreens().map((s) =>
      s.id === "S-04" ? { id: s.id, paths: ["/manual-v2"] } : s,
    );
    const findings = auditRouteInventory(SCREEN_INVENTORY, mutated, [
      ...allRoutePaths().filter((p) => p !== "/manual"),
      "/manual-v2",
    ]);
    expect(findings.some((f) => f.where === "S-04")).toBe(true);
    expect(findings.some((f) => f.where === "/manual-v2")).toBe(true);
  });

  it("fires on an excess route path", () => {
    const findings = auditRouteInventory(SCREEN_INVENTORY, registryScreens(), [
      ...allRoutePaths(),
      "/extra",
    ]);
    expect(findings.some((f) => f.where === "/extra")).toBe(true);
  });

  it("fires on an invented screen directory", () => {
    const findings = auditScreenDirectories(canonScreenIds(), [...canonScreenIds(), "S-14"]);
    expect(findings.some((f) => f.where === "S-14")).toBe(true);
  });

  it("fires on a missing screen directory", () => {
    const findings = auditScreenDirectories(
      canonScreenIds(),
      canonScreenIds().filter((id) => id !== "S-12"),
    );
    expect(findings.some((f) => f.where === "S-12")).toBe(true);
  });
});
