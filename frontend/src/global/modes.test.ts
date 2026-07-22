import { describe, expect, it } from "vitest";

import { SCREENS } from "../routes/registry";
import { CONTROL_ROLES } from "./contracts/wsRoles";
import {
  ESTOP_MATRIX_SIZE,
  LIVE_LINK_MODES,
  estopMatrix,
} from "./modes";

describe("safety matrix axes", () => {
  it("ranges over the eight LiveLinkModes (FR-GUI-080)", () => {
    expect(LIVE_LINK_MODES).toEqual([
      "IDLE",
      "MANUAL",
      "TELEOP_VR",
      "TELEOP_KER",
      "RECORD",
      "INFERENCE",
      "SIM",
      "MOTOR_SETUP",
    ]);
  });

  it("draws the screen axis from the canonical 13-screen registry", () => {
    expect(SCREENS.length).toBe(13);
  });

  it("enumerates the full 13 x 8 x 2 = 208 matrix with no duplicates", () => {
    const cells = estopMatrix();
    expect(cells.length).toBe(ESTOP_MATRIX_SIZE);
    expect(ESTOP_MATRIX_SIZE).toBe(13 * 8 * 2);
    const keys = new Set(cells.map((c) => `${c.screen}|${c.mode}|${c.role}`));
    expect(keys.size).toBe(cells.length);
  });

  it("covers every screen, every mode, and both roles", () => {
    const cells = estopMatrix();
    expect(new Set(cells.map((c) => c.screen)).size).toBe(SCREENS.length);
    expect(new Set(cells.map((c) => c.mode)).size).toBe(LIVE_LINK_MODES.length);
    expect(new Set(cells.map((c) => c.role))).toEqual(new Set(CONTROL_ROLES));
  });
});
