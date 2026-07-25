// Presentation-ordering proofs: the severity sort reorders backend states without
// computing or thresholding anything, a not-landed subsystem resolves to
// UNAVAILABLE (never OK), and the CRITICAL set is the backend's `critical` flag.

import { describe, expect, it } from "vitest";

import { bySeverity, criticalSubsystems, subsystemRenderState } from "./severity";
import type { DiagnosticState, SubsystemId, SubsystemStatus } from "./types";

function status(
  id: SubsystemId,
  state: DiagnosticState | null,
  critical = false,
): SubsystemStatus {
  return { id, label: id, status: state, detail: "", critical };
}

describe("subsystemRenderState", () => {
  it("resolves a null (not-landed) status to UNAVAILABLE, never OK", () => {
    expect(subsystemRenderState(status("can", null))).toBe("UNAVAILABLE");
  });

  it("passes each of the four diagnostic states through verbatim", () => {
    expect(subsystemRenderState(status("can", "OK"))).toBe("OK");
    expect(subsystemRenderState(status("can", "WARN"))).toBe("WARN");
    expect(subsystemRenderState(status("can", "ERROR"))).toBe("ERROR");
    expect(subsystemRenderState(status("can", "STALE"))).toBe("STALE");
  });
});

describe("bySeverity ordering", () => {
  it("orders ERROR, STALE, WARN, UNAVAILABLE, OK — a gap above the greens", () => {
    const input: SubsystemStatus[] = [
      status("can", "OK"),
      status("motors", null),
      status("control_loop", "WARN"),
      status("cameras", "ERROR"),
      status("vr_link", "STALE"),
    ];
    const ordered = bySeverity(input).map((subsystem) => subsystemRenderState(subsystem));
    expect(ordered).toEqual(["ERROR", "STALE", "WARN", "UNAVAILABLE", "OK"]);
  });

  it("keeps every input row (reorders, drops none)", () => {
    const input: SubsystemStatus[] = [
      status("can", "OK"),
      status("motors", "OK"),
      status("control_loop", null),
    ];
    expect(bySeverity(input).length).toBe(input.length);
  });
});

describe("criticalSubsystems", () => {
  it("returns exactly the backend-flagged critical rows", () => {
    const input: SubsystemStatus[] = [
      status("gui_backend", "STALE", true),
      status("can", "OK", false),
      status("motors", "ERROR", true),
    ];
    const critical = criticalSubsystems(input).map((subsystem) => subsystem.id);
    expect(critical).toEqual(["gui_backend", "motors"]);
  });
});
