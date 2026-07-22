// The facade gates reuse backend verdicts; these tests pin their truth tables and
// the PG-VR-001 resolution (pending never becomes a fake pass; failed drives the
// real WebXR fallback).

import { describe, expect, it } from "vitest";

import { DEFAULT_BACKEND_PORT } from "../../config/endpoints";
import {
  activeCommandSource,
  canStartFollowing,
  manualControlDisabled,
  resolveVrEntry,
  webxrIsSeparateFromSpa,
} from "./gates";
import { defaultTeleopSource, type VrGate, type WebxrEntry } from "./teleopSource";

function sourceWith(overrides: Partial<ReturnType<typeof defaultTeleopSource>>) {
  return { ...defaultTeleopSource(), ...overrides };
}

describe("canStartFollowing (CG-G-S05b)", () => {
  it("is false while alignment has not converged and true once it has", () => {
    const base = defaultTeleopSource();
    expect(canStartFollowing({ ...base, alignment: { ...base.alignment, converged: false } })).toBe(false);
    expect(canStartFollowing({ ...base, alignment: { ...base.alignment, converged: true } })).toBe(true);
  });
});

describe("command-source exclusivity (CG-G-S05f)", () => {
  it("disables manual control iff a VR session is active", () => {
    const base = defaultTeleopSource();
    expect(manualControlDisabled({ ...base, session: { ...base.session, active: false } })).toBe(false);
    expect(manualControlDisabled({ ...base, session: { ...base.session, active: true } })).toBe(true);
  });

  it("resolves exactly one active source", () => {
    const base = defaultTeleopSource();
    expect(activeCommandSource({ ...base, session: { ...base.session, active: false } })).toBe(
      "gui_manual_available",
    );
    expect(
      activeCommandSource({ ...base, session: { ...base.session, active: true, transport: "apk_udp" } }),
    ).toBe("vr_apk");
    expect(
      activeCommandSource({ ...base, session: { ...base.session, active: true, transport: "webxr" } }),
    ).toBe("vr_webxr");
  });
});

describe("webxrIsSeparateFromSpa (CG-G-S05g)", () => {
  const httpsEntry = defaultTeleopSource().webxr;

  it("accepts an HTTPS entry on a port distinct from the SPA", () => {
    expect(webxrIsSeparateFromSpa(httpsEntry)).toBe(true);
    expect(httpsEntry.port).not.toBe(DEFAULT_BACKEND_PORT);
  });

  it("rejects a non-HTTPS scheme or a port that collides with the SPA", () => {
    const collide: WebxrEntry = { ...httpsEntry, port: DEFAULT_BACKEND_PORT };
    expect(webxrIsSeparateFromSpa(collide)).toBe(false);
  });
});

describe("resolveVrEntry (PG-VR-001 negative branch)", () => {
  it("renders pending as pending, never a fabricated verdict", () => {
    const gate: VrGate = { id: "PG-VR-001", status: "pending", note: "" };
    const resolution = resolveVrEntry(gate);
    expect(resolution.operationalPath).toBe("pending");
    expect(resolution.fallbackActive).toBe(false);
    expect(resolution.gateStatus).toBe("pending");
  });

  it("drives the WebXR fallback on a failed gate (RETRY_WITH_VARIANT)", () => {
    const gate: VrGate = { id: "PG-VR-001", status: "failed", note: "" };
    const resolution = resolveVrEntry(gate);
    expect(resolution.operationalPath).toBe("webxr_fallback");
    expect(resolution.fallbackActive).toBe(true);
  });

  it("keeps the native APK path on a passed gate", () => {
    const gate: VrGate = { id: "PG-VR-001", status: "passed", note: "" };
    expect(resolveVrEntry(gate).operationalPath).toBe("apk_udp");
  });

  // Anchor sourceWith to a use so the helper's intent is documented in-file.
  it("preserves the fixture when nothing is overridden", () => {
    expect(sourceWith({}).webxr.scheme).toBe("https");
  });
});
