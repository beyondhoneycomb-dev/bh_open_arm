import { describe, expect, it } from "vitest";

import {
  BOUND_SOCKET_SOLE_OWNER,
  CAN_FD_DATA_BITRATE,
  CAN_FD_NOMINAL_BITRATE,
  canStartupBlockers,
  deriveCanState,
  hasIntruder,
  isControlBlocked,
  type CanInterfaceStatus,
} from "./canStatus";

function baseStatus(overrides: Partial<CanInterfaceStatus> = {}): CanInterfaceStatus {
  return {
    iface: "can0",
    flockHeld: true,
    boundSocketCount: 1,
    intruderPids: [],
    linkState: "ERROR-ACTIVE",
    canFdConfigured: true,
    ...overrides,
  };
}

describe("CG-G-03e bound-socket > 1 blocks control and flags an intruder", () => {
  it("treats one bound socket as the sole legitimate owner", () => {
    expect(BOUND_SOCKET_SOLE_OWNER).toBe(1);
    const clean = baseStatus({ boundSocketCount: 1 });
    expect(hasIntruder(clean)).toBe(false);
    expect(isControlBlocked(clean)).toBe(false);
  });

  it("blocks control when a second socket appears and we hold the lock (INTRUDED)", () => {
    const intruded = baseStatus({ boundSocketCount: 2, intruderPids: [4321], flockHeld: true });
    expect(hasIntruder(intruded)).toBe(true);
    expect(deriveCanState(intruded)).toBe("INTRUDED");
    expect(isControlBlocked(intruded)).toBe(true);
  });

  it("blocks control when a second socket appears and we do not hold the lock (CONFLICT)", () => {
    const conflict = baseStatus({ boundSocketCount: 2, flockHeld: false, intruderPids: [999] });
    expect(deriveCanState(conflict)).toBe("CONFLICT");
    expect(isControlBlocked(conflict)).toBe(true);
  });
});

describe("CG-G-03h CAN-FD unset blocks startup", () => {
  it("reports a startup blocker when CAN-FD is not configured", () => {
    const blockers = canStartupBlockers(baseStatus({ canFdConfigured: false }));
    expect(blockers.length).toBe(1);
    expect(blockers[0]).toMatch(/CAN-FD/);
  });

  it("reports no startup blocker when CAN-FD is configured", () => {
    expect(canStartupBlockers(baseStatus({ canFdConfigured: true }))).toEqual([]);
  });

  it("pins the CAN-FD bitrates the link must carry", () => {
    expect(CAN_FD_NOMINAL_BITRATE).toBe(1_000_000);
    expect(CAN_FD_DATA_BITRATE).toBe(5_000_000);
  });
});

describe("CAN state derivation", () => {
  it("is OWNED when the lock is held cleanly", () => {
    expect(deriveCanState(baseStatus({ flockHeld: true }))).toBe("OWNED");
  });

  it("is UNOWNED when the lock is not held and the bus is clean", () => {
    expect(deriveCanState(baseStatus({ flockHeld: false }))).toBe("UNOWNED");
  });

  it("is FAULT on BUS-OFF", () => {
    expect(deriveCanState(baseStatus({ linkState: "BUS-OFF" }))).toBe("FAULT");
    expect(isControlBlocked(baseStatus({ linkState: "BUS-OFF" }))).toBe(true);
  });

  it("prioritises an intruder over a BUS-OFF fault", () => {
    expect(
      deriveCanState(baseStatus({ boundSocketCount: 2, linkState: "BUS-OFF", flockHeld: true })),
    ).toBe("INTRUDED");
  });
});
