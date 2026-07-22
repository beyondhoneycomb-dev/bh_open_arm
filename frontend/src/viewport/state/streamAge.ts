// Stream age and control gating (CG-G-02e). The viewport watches how old the last
// fully accepted snapshot is. Once that age crosses the stale threshold the view
// is marked stale (colour + badge) and EVERY control input is blocked — a stale
// picture must not accept commands against a pose that has moved on.
//
// Recovery is by fresh frames alone. When a new accepted snapshot arrives the age
// resets and control unblocks on its own; there is no reconnect and no connect
// action anywhere in the path (I-2: connect() destroys the zeroing, and the
// browser retries only the WebSocket, which is WP-G-01's concern, not a button
// the operator presses). The viewport's recovery is passive: it waits for data.

import { STREAM_STALE_AGE_MS } from "../constants";

export interface StreamAgeState {
  // Age of the last accepted snapshot in milliseconds.
  readonly ageMs: number;
  // Whether that age is over the stale threshold.
  readonly stale: boolean;
  // Whether control input is blocked. Blocked exactly when stale — the viewport
  // never lets input through on a stale view.
  readonly controlBlocked: boolean;
}

// Evaluate stream age. `lastAcceptedMonoMs` is null before any frame is accepted,
// which reads as maximally stale (no live data is not "everything is fine").
export function evaluateStreamAge(
  lastAcceptedMonoMs: number | null,
  nowMonoMs: number,
  thresholdMs: number = STREAM_STALE_AGE_MS,
): StreamAgeState {
  if (lastAcceptedMonoMs === null) {
    return { ageMs: Number.POSITIVE_INFINITY, stale: true, controlBlocked: true };
  }
  const ageMs = Math.max(0, nowMonoMs - lastAcceptedMonoMs);
  const stale = ageMs > thresholdMs;
  return { ageMs, stale, controlBlocked: stale };
}

// Whether a control input may be issued given the current age state. The single
// question every control affordance asks before it acts.
export function controlInputAllowed(state: StreamAgeState): boolean {
  return !state.controlBlocked;
}
