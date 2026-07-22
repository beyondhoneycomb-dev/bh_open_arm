// CG-G-S02e (unit): CAN-FD unverified blocks startup. The verdict folds the
// foundation's per-interface canStartupBlockers across every interface, so S-02
// states no CAN-FD value of its own.

import { describe, expect, it } from "vitest";

import type { CanInterfaceStatus } from "../../global";
import { canStartupBlockersAll, startupBlockedByCan } from "./canFd";

function iface(name: string, canFdConfigured: boolean): CanInterfaceStatus {
  return {
    iface: name,
    flockHeld: true,
    boundSocketCount: 1,
    intruderPids: [],
    linkState: "ERROR-ACTIVE",
    canFdConfigured,
  };
}

describe("CG-G-S02e CAN-FD startup gate", () => {
  it("blocks startup when no interface exists — nothing to verify is not verified", () => {
    expect(startupBlockedByCan([])).toBe(true);
  });

  it("blocks startup while any interface has CAN-FD unverified", () => {
    const interfaces = [iface("can0", true), iface("can1", false)];
    expect(startupBlockedByCan(interfaces)).toBe(true);
    expect(canStartupBlockersAll(interfaces).length).toBeGreaterThan(0);
  });

  it("clears startup only when every interface has CAN-FD verified", () => {
    const interfaces = [iface("can0", true), iface("can1", true)];
    expect(startupBlockedByCan(interfaces)).toBe(false);
    expect(canStartupBlockersAll(interfaces)).toEqual([]);
  });
});
