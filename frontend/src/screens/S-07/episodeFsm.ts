// The episode-loop view FSM (WP-G-S07): start -> success/fail/cancel -> reset ->
// repeat. This is a PRESENTATION state machine — it governs which control is
// offered when — not the record_loop, which the backend owns. Each transition that
// changes recording state maps to exactly one RecorderCommand intent; the FSM
// decides nothing about the robot and clamps nothing. The safety stop is not part
// of this machine (CG-G-S07a): session stop here is `session_stop`, an episode
// control, and the E-Stop stays in the WP-G-03 global surface.

import type { RecorderCommand } from "./commands";

// idle    — session inactive; the operator may start the session.
// recording — the record_loop is capturing the current episode.
// reset   — the episode ended with a verdict; the loop advances to the next.
export const EPISODE_PHASES = ["idle", "recording", "reset"] as const;
export type EpisodePhase = (typeof EPISODE_PHASES)[number];

// start  — begin the session (idle -> recording).
// success/fail — end + keep the current episode with a verdict (recording -> reset).
// cancel — discard and re-record the current episode (recording -> reset).
// advance — move on to the next episode, i.e. "repeat" (reset -> recording).
// stop   — stop the whole session (any active phase -> idle).
export const EPISODE_EVENTS = [
  "start",
  "success",
  "fail",
  "cancel",
  "advance",
  "stop",
] as const;
export type EpisodeEvent = (typeof EPISODE_EVENTS)[number];

const TRANSITIONS: Record<EpisodePhase, Partial<Record<EpisodeEvent, EpisodePhase>>> = {
  idle: { start: "recording" },
  recording: { success: "reset", fail: "reset", cancel: "reset", stop: "idle" },
  reset: { advance: "recording", stop: "idle" },
};

// The phase an event moves to, or null when the event is not allowed from `phase`.
// A null result is what disables the corresponding control in the view.
export function nextPhase(phase: EpisodePhase, event: EpisodeEvent): EpisodePhase | null {
  return TRANSITIONS[phase][event] ?? null;
}

export function isAllowed(phase: EpisodePhase, event: EpisodeEvent): boolean {
  return nextPhase(phase, event) !== null;
}

// The command intent an event emits, or null when the event only advances the view
// (the "repeat" reset carries no command — the backend loop is already recording).
// `start` needs the task prompt so the first frame is labelled.
export function commandForEvent(event: EpisodeEvent, task: string): RecorderCommand | null {
  switch (event) {
    case "start":
      return { op: "session_start", task };
    case "success":
      return { op: "episode_end", verdict: "success" };
    case "fail":
      return { op: "episode_end", verdict: "fail" };
    case "cancel":
      return { op: "episode_rerecord" };
    case "stop":
      return { op: "session_stop" };
    case "advance":
      return null;
  }
}
