import { describe, expect, it } from "vitest";

import {
  adoptLease,
  classifyLease,
  isLeaseActive,
  leaseRemaining,
  requiresStopHold,
  type ControlLease,
  type LeaseClock,
} from "./lease";

const MAX_AGE_MS = 2000;

function clock(nowMonoServer: number, nowMonoClient: number): LeaseClock {
  return { nowMonoServer, nowMonoClient };
}

function lease(overrides: Partial<ControlLease>): ControlLease {
  return {
    sessionId: "sess-A",
    leaseGeneration: 5,
    expiryMonoServer: 10_000,
    sequence: 100,
    issuedMonoClient: 50_000,
    ...overrides,
  };
}

describe("lease validity (U-4 dead-man)", () => {
  it("is active while the server expiry is in the future", () => {
    expect(isLeaseActive(lease({ expiryMonoServer: 10_000 }), clock(9_000, 0))).toBe(true);
  });

  it("is not active once the server expiry has passed", () => {
    expect(isLeaseActive(lease({ expiryMonoServer: 10_000 }), clock(10_000, 0))).toBe(false);
  });

  it("reports remaining dead-man margin, never negative", () => {
    expect(leaseRemaining(lease({ expiryMonoServer: 10_000 }), clock(9_400, 0))).toBe(600);
    expect(leaseRemaining(lease({ expiryMonoServer: 10_000 }), clock(11_000, 0))).toBe(0);
  });
});

describe("anti-replay classification (CG-G-04d, FR-OPS-091)", () => {
  it("accepts a fresh frame when no lease is held", () => {
    expect(classifyLease(null, lease({}), clock(9_000, 50_500), MAX_AGE_MS)).toBe("accepted");
  });

  it("rejects an expired lease", () => {
    const incoming = lease({ expiryMonoServer: 8_000 });
    expect(classifyLease(null, incoming, clock(9_000, 50_500), MAX_AGE_MS)).toBe("rejected_expired");
  });

  it("rejects a regressed sequence within the same generation as replay", () => {
    const current = lease({ leaseGeneration: 5, sequence: 100 });
    const regressed = lease({ leaseGeneration: 5, sequence: 99 });
    expect(classifyLease(current, regressed, clock(9_000, 50_500), MAX_AGE_MS)).toBe(
      "rejected_replay",
    );
  });

  it("rejects a duplicate (equal) sequence as replay", () => {
    const current = lease({ leaseGeneration: 5, sequence: 100 });
    const duplicate = lease({ leaseGeneration: 5, sequence: 100 });
    expect(classifyLease(current, duplicate, clock(9_000, 50_500), MAX_AGE_MS)).toBe(
      "rejected_replay",
    );
  });

  it("rejects a lease generation below the current one as a takeover victim", () => {
    const current = lease({ leaseGeneration: 6 });
    const stale = lease({ leaseGeneration: 5, sequence: 999 });
    expect(classifyLease(current, stale, clock(9_000, 50_500), MAX_AGE_MS)).toBe(
      "rejected_stale_generation",
    );
  });

  it("discards a frame whose client timestamp is older than the age window", () => {
    const incoming = lease({ issuedMonoClient: 40_000 });
    expect(classifyLease(null, incoming, clock(9_000, 50_500), MAX_AGE_MS)).toBe("discarded_aged");
  });

  it("accepts a newer generation that resets the sequence baseline", () => {
    const current = lease({ leaseGeneration: 5, sequence: 100 });
    const takeover = lease({ leaseGeneration: 6, sequence: 1 });
    expect(classifyLease(current, takeover, clock(9_000, 50_500), MAX_AGE_MS)).toBe("accepted");
  });
});

describe("lease adoption", () => {
  it("adopts an accepted frame", () => {
    const incoming = lease({ leaseGeneration: 6, sequence: 1 });
    const result = adoptLease(lease({ leaseGeneration: 5 }), incoming, clock(9_000, 50_500), MAX_AGE_MS);
    expect(result.verdict).toBe("accepted");
    expect(result.lease).toBe(incoming);
  });

  it("keeps the current lease when a frame is rejected", () => {
    const current = lease({ leaseGeneration: 5, sequence: 100 });
    const replay = lease({ leaseGeneration: 5, sequence: 100 });
    const result = adoptLease(current, replay, clock(9_000, 50_500), MAX_AGE_MS);
    expect(result.verdict).toBe("rejected_replay");
    expect(result.lease).toBe(current);
  });
});

describe("client event -> STOP_HOLD (CG-G-04h, FR-GUI-093)", () => {
  it("holds when the controlling client loses its heartbeat", () => {
    expect(requiresStopHold({ kind: "heartbeat_loss", controlling: true })).toBe(true);
  });

  it("does not hold when a WS client merely leaves — the server keeps authority", () => {
    expect(requiresStopHold({ kind: "leave", controlling: true })).toBe(false);
    expect(requiresStopHold({ kind: "leave", controlling: false })).toBe(false);
  });

  it("does not hold on an observer heartbeat loss — an observer holds no lease", () => {
    expect(requiresStopHold({ kind: "heartbeat_loss", controlling: false })).toBe(false);
  });
});
