// Teleop operator intents (WP-G-S05). The screen sends these to the backend over
// the WS command channel; it never applies them locally. Scale, smoother, deadman
// and heartbeat values are backend-owned — the screen ships the requested value and
// the backend clamps/validates/applies it (the facade rule). Session control is
// session control, not safety: `stop_teleop` is the home-hold end (no disable_torque,
// no drop) and is NOT the soft/hard stop, which is the global WP-G-03 control.
//
// `re_engage` is the one recovery affordance: it requests the backend to leave a
// hold (S5/S6/S7) back into ALIGNING (S3) — never straight into FOLLOWING, which is
// a `05` §4.2 forbidden transition the backend enforces (FR-TEL-082).

export type TeleopCommand =
  | { op: "start_teleop" }
  | { op: "stop_teleop" }
  | { op: "re_engage" }
  | { op: "set_position_scale"; value: number }
  | { op: "set_rotation_scale"; value: number }
  | { op: "set_smoother_params"; minCutoffHz: number; beta: number; dCutoff: number }
  | { op: "set_deadman_threshold"; value: number }
  | { op: "set_heartbeat_timeout"; valueMs: number };

export interface TeleopCommandSink {
  send(command: TeleopCommand): void;
}

export const noopCommandSink: TeleopCommandSink = {
  send() {},
};
