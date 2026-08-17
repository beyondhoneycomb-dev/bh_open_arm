// Turning the WS client's lease snapshot into what the lease view renders.
//
// The two shapes are close and not the same: the renewer tracks a status and the last reject
// reason, the view wants the five `FR-GUI-092` lease fields and a verdict. This is the join, and
// it lives in the shell because neither side may reach the other — `frontend/src/ws/**` is
// WP-G-01's and `frontend/src/mode/**` is WP-G-04's.
//
// The server sends six reject reasons and the view labels five verdicts, and only three of them
// are the same three. `rejected_latched`, `rejected_unarmed` and `rejected_unknown_generation`
// have no label, so they are passed through as the server's own words rather than forced into a
// verdict that means something else — `rejected_latched` in particular is the one an operator
// most needs to read, because it says the arm is held and a re-arm is owed.

import { describe, expect, it } from "vitest";

import type { LeaseSnapshot } from "../ws/leaseRenewer";
import {
  leaseFromSnapshot,
  rejectReasonFromSnapshot,
  roleFromSnapshot,
  verdictFromSnapshot,
} from "./leaseView";

const HELD: LeaseSnapshot = {
  status: "held",
  sessionId: "s-1",
  generation: 3,
  sequence: 7,
  expiryMonoServer: 1_234.5,
  lastRejectReason: null,
};

const NEVER_GRANTED: LeaseSnapshot = {
  status: "unknown",
  sessionId: null,
  generation: null,
  sequence: 0,
  expiryMonoServer: null,
  lastRejectReason: null,
};

describe("leaseFromSnapshot", () => {
  it("carries the five lease fields the view shows", () => {
    const lease = leaseFromSnapshot(HELD);

    expect(lease).not.toBeNull();
    expect(lease?.sessionId).toBe("s-1");
    expect(lease?.leaseGeneration).toBe(3);
    expect(lease?.sequence).toBe(7);
    expect(lease?.expiryMonoServer).toBe(1_234.5);
  });

  it("reports no lease rather than an expired one before the first grant", () => {
    expect(leaseFromSnapshot(NEVER_GRANTED)).toBeNull();
  });

  it("reports no lease when the server granted no expiry", () => {
    // The expiry is the server's word that a lease exists. Substituting a zero would render as
    // a lease that expired at the start of time, which the view draws as expired — and an
    // operator reading that goes looking for control they never had.
    expect(leaseFromSnapshot({ ...HELD, expiryMonoServer: null })).toBeNull();
  });
});

describe("roleFromSnapshot", () => {
  it("is the operator role only while the lease is held", () => {
    expect(roleFromSnapshot(HELD)).toBe("operator");
  });

  it("is observer in every other status", () => {
    // Latched and re-arming are not control: the arm is held and the operator owes the re-arm
    // handshake. Rendering either as controlling shows authority the server would refuse.
    for (const status of ["unknown", "latched", "rearming", "observer"] as const) {
      expect(roleFromSnapshot({ ...HELD, status })).toBe("observer");
    }
  });
});

describe("verdictFromSnapshot", () => {
  it("has no verdict when nothing was rejected", () => {
    expect(verdictFromSnapshot(HELD)).toBeNull();
  });

  it("maps the three reasons the view has a label for", () => {
    expect(verdictFromSnapshot({ ...HELD, lastRejectReason: "rejected_stale_generation" })).toBe(
      "rejected_stale_generation",
    );
    expect(verdictFromSnapshot({ ...HELD, lastRejectReason: "rejected_replay" })).toBe(
      "rejected_replay",
    );
    expect(verdictFromSnapshot({ ...HELD, lastRejectReason: "discarded_aged" })).toBe(
      "discarded_aged",
    );
  });

  it("gives no verdict for a reason the view has no label for", () => {
    // Forcing one of the five labels onto `rejected_latched` would tell the operator their
    // renewal was a replay, which sends them looking for a second client instead of at the
    // latch they have to clear.
    for (const reason of [
      "rejected_latched",
      "rejected_unarmed",
      "rejected_unknown_generation",
    ] as const) {
      expect(verdictFromSnapshot({ ...HELD, lastRejectReason: reason })).toBeNull();
    }
  });
});

describe("rejectReasonFromSnapshot", () => {
  it("carries every refusal through, labelled or not", () => {
    // The three the view cannot label are exactly the three that would otherwise vanish, so the
    // raw reason travels for all of them.
    expect(rejectReasonFromSnapshot({ ...HELD, lastRejectReason: "rejected_latched" })).toBe(
      "rejected_latched",
    );
    expect(rejectReasonFromSnapshot({ ...HELD, lastRejectReason: "rejected_replay" })).toBe(
      "rejected_replay",
    );
  });

  it("is null when nothing was refused", () => {
    expect(rejectReasonFromSnapshot(HELD)).toBeNull();
  });
});
