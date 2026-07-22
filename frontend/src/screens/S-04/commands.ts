// Manual-motion command intents (WP-G-S04). The screen is a FACADE: it SENDS
// operator intent and never computes the motion. The jog math, the two-stage
// clamp (canonical mechanical limit then operating profile, FR-MAN-007), the
// velocity/step guards (FR-MAN-011/012) and the stop category (Cat 2 hold,
// FR-MAN-009/052) are all owned by the backend MAN domain (04). Nothing here
// clamps a value, limits a velocity, or converts deg<->rad — those would be a
// second source of truth (CG-G-S04a).
//
// Every field below is a selection or a direction, not a computed command: a
// step-size or speed-scale the operator picked, a joint/axis/frame they chose, a
// +/- direction. The backend re-derives and re-clamps the actual MIT frame from
// these intents, so the browser can never disagree with the robot about limits.

import type { ArmSide, ReferenceFrame } from "./manualSource";

// Re-exported so command consumers import the frame type from one place; the sole
// definition lives with the other backend-facing types in manualSource.
export type { ReferenceFrame };

export type JogMode = "continuous" | "step";
export type JogDirection = "positive" | "negative";
export type CartesianAxis = "x" | "y" | "z" | "roll" | "pitch" | "yaw";

// A joint jog intent: which arm, which joint (1..8, J8 = gripper), which way, and
// the operator's mode/step/speed selections carried through unchanged.
export interface JogJointCommand {
  op: "jog_joint";
  side: ArmSide;
  jointIndex: number;
  direction: JogDirection;
  mode: JogMode;
  // Operator's chosen step size (step mode) and global speed scale. Both are
  // selections, not limits — the backend applies the real velocity guard.
  stepSizeDeg: number | null;
  speedScalePct: number;
}

// Cat 2 hold intent (FR-MAN-009): change the command to STOP_HOLD. This is NOT
// the hard E-Stop (power cut) — that stays the global surface's control (WP-G-03),
// visually and structurally distinct. The stop CATEGORY is the backend's.
export interface StopHoldCommand {
  op: "stop_hold";
  side: ArmSide;
}

export interface JogCartesianCommand {
  op: "jog_cartesian";
  side: ArmSide;
  axis: CartesianAxis;
  direction: JogDirection;
  frame: ReferenceFrame;
  mode: JogMode;
  stepSize: number | null;
  speedScalePct: number;
}

// Nullspace (elbow swivel) intent. eeHold declares the end-effector pose is held:
// a pure redundancy motion, so the EE translation/rotation delta is exactly zero
// (CG-G-S04i). The backend moves the elbow while keeping the EE where it is.
export interface JogNullspaceCommand {
  op: "jog_nullspace";
  side: ArmSide;
  elbowDelta: number;
  eeHold: true;
  eeDeltaXyzMm: readonly [0, 0, 0];
  eeDeltaRpyDeg: readonly [0, 0, 0];
}

// Freedrive is hold-to-activate (FR-MAN-029): enter on press, exit-to-hold on
// release. The gravity/friction compensation is the backend's; the screen only
// signals the deadman edge.
export interface FreedriveCommand {
  op: "freedrive_enter" | "freedrive_exit";
  side: ArmSide;
}

// Enable/disable torque = the explicit arm step (0xFC/0xFD). This is NOT connect()
// (I-2): it never re-opens the session and never re-zeroes. Motion intents are
// refused until torque is armed (CG-G-S04b).
export interface ArmCommand {
  op: "enable_torque" | "disable_torque";
  side: ArmSide;
}

// Replay/home execution intents. The backend pre-verifies the whole trajectory
// (FR-MAN-044/048); the screen only gates the button on that verdict (CG-G-S04h).
export interface HomeExecuteCommand {
  op: "home_execute";
  profileId: string;
  side: ArmSide;
}

export interface ReplayExecuteCommand {
  op: "replay_execute";
  pointId: string;
  side: ArmSide;
}

export type ManualCommand =
  | JogJointCommand
  | StopHoldCommand
  | JogCartesianCommand
  | JogNullspaceCommand
  | FreedriveCommand
  | ArmCommand
  | HomeExecuteCommand
  | ReplayExecuteCommand;

// The sink a screen publishes intents to. In production this wraps the single WS
// client's control-frame send (WP-G-01), where the server is the authority that
// accepts or refuses the frame by lease/role — the browser never decides motion.
// The default is a no-op so the AI-offline lane drives the screen with a recorder.
export interface ManualCommandSink {
  send(command: ManualCommand): void;
}

export const noopCommandSink: ManualCommandSink = {
  send: () => {},
};

// Project a command intent onto the frozen CTR-WS command frame body. Kept
// separate from the sink so the wire shape is testable without a socket.
export function commandToWire(command: ManualCommand): Record<string, unknown> {
  return { type: "command", ...command };
}
