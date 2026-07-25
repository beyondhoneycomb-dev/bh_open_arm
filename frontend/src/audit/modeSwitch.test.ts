// CG-5-04e — mode switching is a state transition, not a process restart: zero
// connect()/disconnect() calls in GUI code paths. connect() re-runs
// set_zero_position(), so a mode change must move the send_action authority, never
// re-open the Robot. Real tree: no shipped source names a connect()/disconnect() call
// (the WS client opens a socket, never the backend Robot). Synthetic: a Robot
// connect() and a disconnect() both make the audit fire. The pattern carries the
// forbidden token, so it lives here.

import { describe, expect, it } from "vitest";

import { scanForPatterns } from "./scan";
import type { NamedPattern } from "./types";
import { shippedSpaSources } from "./testSupport/collect";

const SESSION_REOPEN: NamedPattern[] = [
  { label: "Robot connect()/disconnect() call", pattern: /\b(?:dis)?connect\s*\(/ },
];

describe("CG-5-04e mode switch is a state transition (0 connect()/disconnect())", () => {
  it("no shipped source names a Robot connect()/disconnect() call", () => {
    expect(scanForPatterns(shippedSpaSources(), SESSION_REOPEN, "CG-5-04e")).toEqual([]);
  });

  it("fires on a Robot connect() call", () => {
    const findings = scanForPatterns(
      [{ path: "fake/x.ts", code: "await robot.connect();" }],
      SESSION_REOPEN,
      "CG-5-04e",
    );
    expect(findings.length).toBeGreaterThan(0);
  });

  it("fires on a disconnect() call", () => {
    const findings = scanForPatterns(
      [{ path: "fake/x.ts", code: "robot.disconnect();" }],
      SESSION_REOPEN,
      "CG-5-04e",
    );
    expect(findings.length).toBeGreaterThan(0);
  });

  it("does not fault a same-word identifier like connection or openSocket", () => {
    const findings = scanForPatterns(
      [{ path: "fake/x.ts", code: "const s = loadConnection(); this.openSocket();" }],
      SESSION_REOPEN,
      "CG-5-04e",
    );
    expect(findings).toEqual([]);
  });
});
