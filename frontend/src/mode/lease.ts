// The control-authority lease and its anti-replay classification (FR-GUI-092,
// FR-OPS-091, CG-G-04d). The lease is the WP-2A-02 dead-man canon transported over
// CTR-WS@v1 — this module TRANSPORTS and RENDERS it, it does not redefine the
// lease semantics. The server is the authority: expiry is judged server-side
// (CTR-WS lease.expiry_judge_role = "server") and the server rejects stale/replayed
// commands. The browser classifies incoming lease frames only so it never RENDERS
// a stale, replayed or expired lease as "you are in control" — a false "controlling"
// badge would let an operator send commands under a lease the server has already
// invalidated (CG-G-04d negative branch = control takeover).
//
// Field mapping to CTR-WS@v1 lease_grant: expiry <- expiry_mono_server (server
// owns it), timestamp <- issued_mono_client (client stamps it). FR-GUI-092's lease
// shape {session_id, lease_generation, expiry, sequence, timestamp} is exactly
// these five fields.

export interface ControlLease {
  sessionId: string;
  // Bumped on every force-release so an old holder's residual frames are stale
  // (FR-OPS-091). A lower generation than the current one is a takeover victim's
  // replay.
  leaseGeneration: number;
  // Server-owned expiry on the server monotonic clock (CTR-WS expiry_mono_server).
  // The client frame carries no expiry (CTR-WS client_frame_carries_no_expiry).
  expiryMonoServer: number;
  // Monotone per generation. A sequence that does not advance is a replay.
  sequence: number;
  // Client-stamped issue time (CTR-WS issued_mono_client), used for the age filter.
  issuedMonoClient: number;
}

// Two clocks because expiry lives on the server clock and the age filter lives on
// the client clock (CTR-WS lease.age_filter.age_input_role = "client").
export interface LeaseClock {
  nowMonoServer: number;
  nowMonoClient: number;
}

// The verdict on an incoming lease frame, drawn from CTR-WS lease.reject_reasons
// plus "accepted" and the server-expiry verdict "rejected_expired". Anything other
// than "accepted" must not be adopted as the controlling lease.
export type LeaseVerdict =
  | "accepted"
  | "rejected_expired" // expiry_mono_server already passed (server-judged expiry)
  | "rejected_stale_generation" // generation below the current one (takeover victim)
  | "rejected_replay" // sequence did not advance (regression or duplicate)
  | "discarded_aged"; // issued_mono_client older than the age window

// Whether a currently held lease is still live, or has expired and dropped the
// client to no authority. Expiry is the U-4 dead-man: absence of renewal past the
// server expiry = auto-hold, so an expired lease is never "active".
export function isLeaseActive(lease: ControlLease, clock: LeaseClock): boolean {
  return lease.expiryMonoServer > clock.nowMonoServer;
}

// Remaining lease time in server-clock units; never negative. The control-lease
// view renders this as the standing dead-man margin (FR-GUI-092, U-4) so a coming
// auto-hold is visible before it happens.
export function leaseRemaining(lease: ControlLease, clock: LeaseClock): number {
  const remaining = lease.expiryMonoServer - clock.nowMonoServer;
  return remaining > 0 ? remaining : 0;
}

// Classify an incoming lease frame against the lease currently adopted (or null
// when none is held). Order matters: an expired or under-age frame is rejected
// before generation/sequence, because a frame that fails the clock filters is not
// worth comparing to the held lease.
export function classifyLease(
  current: ControlLease | null,
  incoming: ControlLease,
  clock: LeaseClock,
  maxAgeMs: number,
): LeaseVerdict {
  if (incoming.expiryMonoServer <= clock.nowMonoServer) {
    return "rejected_expired";
  }
  if (clock.nowMonoClient - incoming.issuedMonoClient > maxAgeMs) {
    return "discarded_aged";
  }
  if (current === null) {
    return "accepted";
  }
  if (incoming.leaseGeneration < current.leaseGeneration) {
    return "rejected_stale_generation";
  }
  // Within the same generation the sequence must strictly advance; an equal or
  // lower sequence is a duplicate replay or a regression. A newer generation
  // (force-takeover) resets the sequence baseline, so it is not a replay.
  if (
    incoming.leaseGeneration === current.leaseGeneration &&
    incoming.sequence <= current.sequence
  ) {
    return "rejected_replay";
  }
  return "accepted";
}

// Adopt an incoming frame only when it classifies as accepted; otherwise keep the
// current lease and report why the frame was refused. The view uses `verdict` to
// render the last reject reason and `lease` to decide the controlling badge.
export interface LeaseAdoption {
  lease: ControlLease | null;
  verdict: LeaseVerdict;
}

export function adoptLease(
  current: ControlLease | null,
  incoming: ControlLease,
  clock: LeaseClock,
  maxAgeMs: number,
): LeaseAdoption {
  const verdict = classifyLease(current, incoming, clock, maxAgeMs);
  return { lease: verdict === "accepted" ? incoming : current, verdict };
}

// A WS-client lifecycle event the control-lease view must react to (FR-GUI-093,
// CG-G-04h). "leave" is a clean WS close; "heartbeat_loss" is the controlling
// loop's renewal/heartbeat timing out while the socket is nominally up.
export type ClientEventKind = "leave" | "heartbeat_loss";

export interface ClientEvent {
  kind: ClientEventKind;
  // Whether the client the event is about currently holds control authority.
  controlling: boolean;
}

// Whether a client event must drive the robot to STOP_HOLD (CG-G-04h). A WS client
// leaving is NEVER a soft-stop cause — the server holds authority and can hand it
// on. Only the CONTROLLING client's heartbeat loss is STOP_HOLD: that is the
// dead-man lease going unrenewed (U-4), which the scheduler turns into an auto-hold.
// An observer's heartbeat loss holds nothing, because an observer holds no lease.
export function requiresStopHold(event: ClientEvent): boolean {
  return event.kind === "heartbeat_loss" && event.controlling;
}
