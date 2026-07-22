import { describe, expect, it } from "vitest";

import { FORBIDDEN_HEALTH_FIELDS, projectPublicHealth } from "./health";

describe("public health projection (CG-G-04g, FR-GUI-092)", () => {
  it("copies allowlisted fields", () => {
    const projected = projectPublicHealth({
      status: "ok",
      uptimeSeconds: 42,
      canLinkUp: true,
    });
    expect(projected).toEqual({ status: "ok", uptimeSeconds: 42, canLinkUp: true });
  });

  it("never carries the control holder or the active profile across", () => {
    const projected = projectPublicHealth({
      status: "ok",
      uptimeSeconds: 42,
      canLinkUp: true,
      control_holder: "sess-secret",
      active_profile: "PFL_HUMAN_NEARBY",
    });
    const serialized = JSON.stringify(projected);
    for (const forbidden of FORBIDDEN_HEALTH_FIELDS) {
      expect(projected).not.toHaveProperty(forbidden);
      expect(serialized).not.toContain(forbidden);
    }
    expect(serialized).not.toContain("sess-secret");
    expect(serialized).not.toContain("PFL_HUMAN_NEARBY");
  });

  it("falls back for missing or malformed fields", () => {
    const projected = projectPublicHealth({ status: 12, canLinkUp: "yes" });
    expect(projected).toEqual({ status: "unknown", uptimeSeconds: 0, canLinkUp: false });
  });
});
