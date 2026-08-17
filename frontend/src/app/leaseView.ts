// The join between the WS client's lease snapshot and the control-lease view.
//
// It lives in the shell because neither side may reach the other: `frontend/src/ws/**` is
// WP-G-01's and `frontend/src/mode/**` is WP-G-04's, and the shell is what already holds both.
//
// The server sends six reject reasons (`LEASE_REJECT_REASONS`) and the view labels five verdicts
// (`LeaseVerdict`); three are the same three. `rejected_latched`, `rejected_unarmed` and
// `rejected_unknown_generation` have no label. They are carried through as the server's own words
// rather than pressed into a verdict that means something else — `rejected_latched` says the arm
// is held and a re-arm handshake is owed, and rendering that as a replay sends the operator
// looking for a second client instead of at the latch.

import type { ControlLease, LeaseVerdict } from "../mode/lease";
import type { LeaseRole } from "../mode/roles";
import type { LeaseSnapshot } from "../ws/leaseRenewer";

// The reject reasons the view has a label for. The rest travel as raw text.
const LABELLED_VERDICTS: Readonly<Record<string, LeaseVerdict>> = {
  rejected_stale_generation: "rejected_stale_generation",
  rejected_replay: "rejected_replay",
  discarded_aged: "discarded_aged",
};

// Build the lease the view renders, or null when this client holds none.
//
// A missing expiry is the whole test for "no lease": the expiry is the server's word that one
// exists, and the client never authors it. Substituting a zero would render as a lease that
// expired at the start of time, which reads as control lost rather than control never held.
export function leaseFromSnapshot(snapshot: LeaseSnapshot): ControlLease | null {
  if (snapshot.sessionId === null || snapshot.expiryMonoServer === null) {
    return null;
  }
  return {
    sessionId: snapshot.sessionId,
    leaseGeneration: snapshot.generation ?? 0,
    expiryMonoServer: snapshot.expiryMonoServer,
    sequence: snapshot.sequence,
    // The renewer stamps its own issue time per frame and does not keep the last one, so the
    // view's age display has nothing behind it here. Zero is the honest filler: the field feeds
    // no decision — expiry is judged on the server clock — and inventing a plausible client
    // timestamp would put a number on screen that describes nothing.
    issuedMonoClient: 0,
  };
}

// Which role this client renders as. Only a held lease is control: latched and re-arming both
// mean the arm is held and the operator owes the re-arm handshake, so neither may draw as
// controlling — the server would refuse a command sent under either.
export function roleFromSnapshot(snapshot: LeaseSnapshot): LeaseRole {
  return snapshot.status === "held" ? "operator" : "observer";
}

// The verdict the view can label, or null when the server's reason has no label here.
export function verdictFromSnapshot(snapshot: LeaseSnapshot): LeaseVerdict | null {
  if (snapshot.lastRejectReason === null) {
    return null;
  }
  return LABELLED_VERDICTS[snapshot.lastRejectReason] ?? null;
}

// The server's own reason for the last refusal, labelled or not. This is what keeps the three
// unlabelled reasons from vanishing.
export function rejectReasonFromSnapshot(snapshot: LeaseSnapshot): string | null {
  return snapshot.lastRejectReason;
}
