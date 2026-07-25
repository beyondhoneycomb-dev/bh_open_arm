// CG-5-02c / FR-OPS-027: the public (unauthenticated) health projection must not
// expose the control-holder or the active-profile id. These prove the projection
// carries neither the field nor the value, even when the authenticated snapshot
// holds both.

import { describe, expect, it } from "vitest";

import { toPublicHealth } from "./health";
import { defaultDashboardData } from "./dashboardSource";

describe("public health projection redaction (CG-5-02c / FR-OPS-027)", () => {
  it("omits the control-holder and active-profile id fields", () => {
    const data = defaultDashboardData();
    const publicHealth = toPublicHealth(data);
    expect("controlHolder" in publicHealth).toBe(false);
    expect("activeProfileId" in publicHealth).toBe(false);
    expect("sessionId" in publicHealth).toBe(false);
  });

  it("leaks neither value even when the authenticated snapshot holds both", () => {
    const data = defaultDashboardData();
    data.connection.controlHolder = "operator@secret-console";
    data.connection.activeProfileId = "profile_secret_47";
    data.connection.sessionId = "sess_secret_xyz";
    const serialized = JSON.stringify(toPublicHealth(data));
    expect(serialized).not.toContain("operator@secret-console");
    expect(serialized).not.toContain("profile_secret_47");
    expect(serialized).not.toContain("sess_secret_xyz");
  });

  it("still surfaces subsystem health and active error codes to the public", () => {
    const data = defaultDashboardData();
    const publicHealth = toPublicHealth(data);
    expect(publicHealth.subsystems.length).toBe(data.subsystems.length);
    expect(publicHealth.subsystems.every((subsystem) => "status" in subsystem)).toBe(true);
    expect(Array.isArray(publicHealth.activeErrorCodes)).toBe(true);
  });
});
