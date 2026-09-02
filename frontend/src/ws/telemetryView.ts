// Read the `telemetry` frame body into what screens render.
//
// Parse-only. Every field is checked before it is used and a field that is absent
// or the wrong shape becomes an absence here, never a plausible number: the frame
// is the last place "no reading" and "a reading of zero" are still different, and
// a screen draws them identically.
//
// The mirror of `contracts/ws/schema.py`'s TELEMETRY row and
// `backend/ws/telemetry.py`'s body. Nothing binds the two across the language
// boundary, so `envelope.contract.test.ts` reads the frozen envelope and this
// file's key names are checked against the backend's constants by a contract test.

import type { DecodedTextFrame } from "./types";

// Body keys, matching `contracts/ws/schema.py`'s TELEMETRY_*_FIELD.
export const TELEMETRY_SEQUENCE_KEY = "sequence";
export const TELEMETRY_OBSERVATION_KEY = "observation";
export const TELEMETRY_MOTOR_STATES_KEY = "motor_states";
export const TELEMETRY_ARMS_KEY = "arms";
export const TELEMETRY_JOINTS_KEY = "joints";

// The vector key inside `observation`, as LeRobot names it.
export const OBSERVATION_STATE_KEY = "observation.state";

// Per-side liveness keys, matching `backend/ws/telemetry.py`.
export const ARM_READ_AGE_KEY = "read_age_s";
export const ARM_STALE_KEY = "stale";
export const ARM_TICK_INDEX_KEY = "tick_index";
export const ARM_OBSERVATION_PRESENT_KEY = "observation_present";
export const ARM_BUS_READ_OK_KEY = "bus_read_ok";
export const ARM_LOCK_ACQUIRED_KEY = "lock_acquired";
export const ARM_RESIDUAL_EXCEEDED_KEY = "residual_exceeded";

// Joint row keys, matching `backend/ws/telemetry.py`.
export const JOINT_NAME_KEY = "name";
export const JOINT_MOTOR_KEY = "motor";
export const JOINT_POSITION_DEG_KEY = "position_deg";
export const JOINT_POSITION_RAD_KEY = "position_rad";
export const JOINT_VELOCITY_DEG_S_KEY = "velocity_deg_s";
export const JOINT_VELOCITY_RAD_S_KEY = "velocity_rad_s";
export const JOINT_TORQUE_NM_KEY = "torque_nm";
export const JOINT_LIMIT_LOWER_DEG_KEY = "limit_lower_deg";
export const JOINT_LIMIT_UPPER_DEG_KEY = "limit_upper_deg";
export const JOINT_LIMIT_LOWER_RAD_KEY = "limit_lower_rad";
export const JOINT_LIMIT_UPPER_RAD_KEY = "limit_upper_rad";
export const JOINT_NEAR_LIMIT_KEY = "near_limit";
export const JOINT_BLOCKED_DIRECTION_KEY = "blocked_direction";

// The three values the backend's `BlockedDirection` can take. Listed so a fourth one — or a
// typo — is read as an unparsable row rather than silently becoming a direction nothing blocks.
const BLOCKED_DIRECTIONS = ["none", "positive", "negative"] as const;

export type BlockedDirection = (typeof BLOCKED_DIRECTIONS)[number];

export interface JointReading {
  // The URDF/MJCF joint this row is about — the name the model and the limits are written
  // against, and what the viewport keys its snapshot by.
  readonly name: string;
  // The LeRobot channel prefix for the same joint, which is how `motor_states` names it. Both
  // travel because the crossing between the two namespaces is the backend's fact, not a string
  // transform a screen should be doing.
  readonly motor: string;
  readonly positionDeg: number;
  // Converted by the backend through the single CTR-UNIT crossing. The browser must not convert
  // — a second rounding disagrees with the first exactly where a value sits on a bound.
  readonly positionRad: number;
  readonly velocityDegPerSec: number;
  readonly velocityRadPerSec: number;
  readonly torqueNm: number;
  readonly limitLowerDeg: number;
  readonly limitUpperDeg: number;
  readonly limitLowerRad: number;
  readonly limitUpperRad: number;
  // Backend verdicts (`04` FR-MAN-013). Rendered, never recomputed: a browser that decided "at
  // limit" from the position would be a second clamp disagreeing with the gateway's.
  readonly nearLimit: boolean;
  readonly blockedDirection: BlockedDirection;
}

export interface ArmLiveness {
  readonly side: string;
  // Seconds since the reading was taken, on the server's clock. This is what
  // separates a board that stopped advancing from an arm that is holding still.
  readonly readAgeS: number;
  // That age already judged, by the only process that knows the rate the board is
  // filled at. True means the reading stopped advancing — the values below are the
  // last ones taken, however long ago that was, and none of them will change again.
  readonly stale: boolean;
  readonly tickIndex: number;
  readonly observationPresent: boolean;
  readonly busReadOk: boolean;
  readonly lockAcquired: boolean;
  readonly residualExceeded: boolean;
}

export interface TelemetryView {
  readonly sequence: number;
  // One float per declared observation channel, in the frozen order. Empty when the
  // frame carried no vector, which is not the same as a vector of zeros.
  readonly observationState: readonly number[];
  // The frame's own body, kept so a screen can read a section this view does not model.
  // `S-03` reads `motor_states` with its own parser, which owns that screen's row type and
  // the missing-`err_nibble` default; re-parsing it here would be a second definition of one
  // shape, and the two would drift the first time either moved.
  readonly body: Record<string, unknown>;
  // Only the sides that have published. A side missing here has taken no reading
  // yet, which is a different fact from a reading that went stale.
  readonly arms: readonly ArmLiveness[];
  // One row per joint of every side that has published, in the backend's order. Empty
  // when the frame carried none, which is not the same as a rig with no joints.
  readonly joints: readonly JointReading[];
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function numberAt(source: Record<string, unknown>, key: string): number | null {
  const value = source[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function boolAt(source: Record<string, unknown>, key: string): boolean | null {
  const value = source[key];
  return typeof value === "boolean" ? value : null;
}

function parseArms(body: Record<string, unknown>): ArmLiveness[] {
  const arms = record(body[TELEMETRY_ARMS_KEY]);
  if (arms === null) {
    return [];
  }
  const parsed: ArmLiveness[] = [];
  for (const side of Object.keys(arms).sort()) {
    const entry = record(arms[side]);
    if (entry === null) {
      continue;
    }
    const readAgeS = numberAt(entry, ARM_READ_AGE_KEY);
    const stale = boolAt(entry, ARM_STALE_KEY);
    const tickIndex = numberAt(entry, ARM_TICK_INDEX_KEY);
    const observationPresent = boolAt(entry, ARM_OBSERVATION_PRESENT_KEY);
    const busReadOk = boolAt(entry, ARM_BUS_READ_OK_KEY);
    const lockAcquired = boolAt(entry, ARM_LOCK_ACQUIRED_KEY);
    const residualExceeded = boolAt(entry, ARM_RESIDUAL_EXCEEDED_KEY);
    // All or nothing. A half-parsed arm would report some guard fields as read and
    // the rest as false, and false is what a healthy field looks like for three of
    // the four — the row would say "lock lost" about a lock nobody asked about.
    if (
      readAgeS === null ||
      stale === null ||
      tickIndex === null ||
      observationPresent === null ||
      busReadOk === null ||
      lockAcquired === null ||
      residualExceeded === null
    ) {
      continue;
    }
    parsed.push({
      side,
      readAgeS,
      stale,
      tickIndex,
      observationPresent,
      busReadOk,
      lockAcquired,
      residualExceeded,
    });
  }
  return parsed;
}

function stringAt(source: Record<string, unknown>, key: string): string | null {
  const value = source[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

function parseJoints(body: Record<string, unknown>): JointReading[] {
  const rows = body[TELEMETRY_JOINTS_KEY];
  if (!Array.isArray(rows)) {
    return [];
  }
  const parsed: JointReading[] = [];
  for (const row of rows) {
    const entry = record(row);
    if (entry === null) {
      continue;
    }
    const name = stringAt(entry, JOINT_NAME_KEY);
    const motor = stringAt(entry, JOINT_MOTOR_KEY);
    const blocked = stringAt(entry, JOINT_BLOCKED_DIRECTION_KEY);
    const nearLimit = boolAt(entry, JOINT_NEAR_LIMIT_KEY);
    const numbers = [
      JOINT_POSITION_DEG_KEY,
      JOINT_POSITION_RAD_KEY,
      JOINT_VELOCITY_DEG_S_KEY,
      JOINT_VELOCITY_RAD_S_KEY,
      JOINT_TORQUE_NM_KEY,
      JOINT_LIMIT_LOWER_DEG_KEY,
      JOINT_LIMIT_UPPER_DEG_KEY,
      JOINT_LIMIT_LOWER_RAD_KEY,
      JOINT_LIMIT_UPPER_RAD_KEY,
    ].map((key) => numberAt(entry, key));
    // All or nothing, for the reason the arm rows are: a half-read joint would show a
    // position against a bound that came from nowhere, and the near-limit warning is
    // exactly a claim about the two together.
    if (
      name === null ||
      motor === null ||
      nearLimit === null ||
      blocked === null ||
      !BLOCKED_DIRECTIONS.includes(blocked as BlockedDirection) ||
      numbers.some((value) => value === null)
    ) {
      continue;
    }
    const [
      positionDeg,
      positionRad,
      velocityDegPerSec,
      velocityRadPerSec,
      torqueNm,
      limitLowerDeg,
      limitUpperDeg,
      limitLowerRad,
      limitUpperRad,
    ] = numbers as number[];
    parsed.push({
      name,
      motor,
      positionDeg,
      positionRad,
      velocityDegPerSec,
      velocityRadPerSec,
      torqueNm,
      limitLowerDeg,
      limitUpperDeg,
      limitLowerRad,
      limitUpperRad,
      nearLimit,
      blockedDirection: blocked as BlockedDirection,
    });
  }
  return parsed;
}

function parseObservation(body: Record<string, unknown>): number[] {
  const observation = record(body[TELEMETRY_OBSERVATION_KEY]);
  const vector = observation === null ? null : observation[OBSERVATION_STATE_KEY];
  if (!Array.isArray(vector)) {
    return [];
  }
  return vector.filter((value): value is number => typeof value === "number");
}

// Read one telemetry frame. Returns null when the body is not one — the caller keeps
// whatever it had, rather than replacing a good reading with a blank one.
export function readTelemetry(frame: DecodedTextFrame): TelemetryView | null {
  if (frame.frameType !== "telemetry") {
    return null;
  }
  const sequence = numberAt(frame.body, TELEMETRY_SEQUENCE_KEY);
  if (sequence === null) {
    return null;
  }
  return {
    sequence,
    observationState: parseObservation(frame.body),
    body: frame.body,
    arms: parseArms(frame.body),
    joints: parseJoints(frame.body),
  };
}
