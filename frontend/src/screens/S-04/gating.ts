// The single facade gate every motion affordance on the manual screen asks before
// it emits (WP-G-S04). It reuses the foundation's own judgements — the control
// lease (WP-G-04 mode/lease) and the viewport's stream-age rule (WP-G-02) — rather
// than inventing its own, so the screen cannot disagree with the rest of the GUI
// about whether control is live.
//
// Two gates, deliberately separate:
//   canArm      — may the operator enable torque? Needs the lease and a fresh
//                 stream. Arming is the explicit precondition motion requires.
//   canIssueMotion(armed) — may a jog/elbow/freedrive intent go out? Needs arm
//                 FIRST (CG-G-S04b): a slider or 3D drag alone, unarmed, sends
//                 nothing.
// Nothing here clamps a value or limits a velocity (CG-G-S04a).

import { isLeaseActive, leaseRemaining } from "../../mode";
import { evaluateStreamAge } from "../../viewport";

import type { ManualSource } from "./manualSource";

export function leaseHeld(source: ManualSource): boolean {
  return isLeaseActive(source.lease, source.clock);
}

export function streamStale(source: ManualSource): boolean {
  return evaluateStreamAge(source.lastFrameMonoMs, source.nowMonoMs).stale;
}

export function canArm(source: ManualSource): boolean {
  return leaseHeld(source) && !streamStale(source);
}

export function canIssueMotion(source: ManualSource, armed: boolean): boolean {
  return armed && canArm(source);
}

export function leaseRemainingMs(source: ManualSource): number {
  return leaseRemaining(source.lease, source.clock);
}

// Dead-man heartbeat margin for DISPLAY only (CG-G-S04d): time left before the
// renewal-absence timeout the backend scheduler turns into an auto-hold (U-4,
// FR-MAN-051). The client-clock age read is the age-input role the lease contract
// already assigns to the client; the timeout enforcement itself stays backend.
export function heartbeatMarginMs(source: ManualSource): number {
  const age = source.clock.nowMonoClient - source.deadman.lastBeatMonoClientMs;
  const margin = source.deadman.heartbeatTimeoutMs - age;
  return margin > 0 ? margin : 0;
}
