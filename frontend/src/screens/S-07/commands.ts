// Episode-control command intents (WP-G-S07). The screen is a FACADE: it SENDS
// operator intent to the backend-owned record_loop `events` dict (WP-3B-11
// acceptance ②) and never drives the recorder itself. Every op below is an
// EPISODE control, never a safety stop: 02d §2.2 fixes that `stop_recording` is
// NOT wired to the E-Stop (CG-G-S07a), because a loop-stopping stop interrupts the
// command stream, drops enable, and zeroes torque — a drop, not a safe stop. The
// hard E-Stop and soft stop live in the WP-G-03 global surface and are structurally
// separate; no op here references them.

// Start the recording session — begins the backend record_loop. Carries the task
// prompt attached to every frame. Gated by the start preconditions (preflight,
// disk headroom, push_to_hub confirm); the backend is the authority that accepts it.
export interface SessionStartCommand {
  op: "session_start";
  task: string;
}

// End the current episode and KEEP it, attaching a human success/fail verdict as a
// sidecar (the label is not in LeRobot natively — 02d §2.2). Maps to the backend
// `request_end_episode` plus the verdict; the backend owns the EpisodeLabel.
export interface EpisodeEndCommand {
  op: "episode_end";
  verdict: "success" | "fail";
}

// Cancel the current episode: discard and re-record it. Maps to the backend
// `request_rerecord` (which also raises exit_early). This drops the current
// episode's data by design; it is not a session stop.
export interface EpisodeRerecordCommand {
  op: "episode_rerecord";
}

// Stop the whole recording session — maps to the backend `request_stop`. This ends
// the record_loop cleanly; it is episode control, not the safety E-Stop.
export interface SessionStopCommand {
  op: "session_stop";
}

// Resume an interrupted session by its STAMPED repo_id, unchanged (CG-G-S07e). The
// backend re-opens the dataset under exactly this id; re-stamping would fork the name.
export interface ResumeCommand {
  op: "resume";
  stampedRepoId: string;
}

// Change the task prompt the backend attaches to subsequent frames.
export interface SetTaskCommand {
  op: "set_task";
  task: string;
}

export type RecorderCommand =
  | SessionStartCommand
  | EpisodeEndCommand
  | EpisodeRerecordCommand
  | SessionStopCommand
  | ResumeCommand
  | SetTaskCommand;

// The sink a screen publishes intents to. In production this wraps the single WS
// client's control-frame send (WP-G-01), where the server accepts or refuses by
// lease/role — the browser never decides recording. The default is a no-op so the
// AI-offline lane drives the screen with a recorder.
export interface RecorderCommandSink {
  send(command: RecorderCommand): void;
}

export const noopCommandSink: RecorderCommandSink = {
  send: () => {},
};

// Project a command intent onto the frozen CTR-WS command frame body. Kept
// separate from the sink so the wire shape is testable without a socket.
export function commandToWire(command: RecorderCommand): Record<string, unknown> {
  return { type: "command", ...command };
}
