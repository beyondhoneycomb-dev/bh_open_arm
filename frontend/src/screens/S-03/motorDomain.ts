// The MOT (03) facade surface for the motor-setup screen (S-03). The screen is a
// window onto backend state, not a canon: motor descriptors, temperatures, error
// nibbles, gain/limit profiles and gripper endpoints are all backend-owned truth
// arrives over the single WS state frame (WP-0B-07 RID read, WP-2A-03 limit
// profile, WP-2A-07 ERR nibble, WP-2A-08 gripper endpoint, WP-2C-11 temp/gripper).
// This module never authors that truth — it declares the shapes the screen
// renders, mirrors the few frozen-contract constants it must recognise, and runs
// the pure guards the acceptance checks require before a save intent is emitted.
//
// The two save guards (kp/kd range, operational ⊆ mechanical) are NOT a second
// source of truth. The backend silently clamps an out-of-range gain (LeRobot
// `_float_to_uint`, 03 §2.8) — the operator would never know the stiffness they
// asked for was quietly cut. The screen's job is to REFUSE loudly with the
// contract's own published bounds, not to clamp-and-send a value of its own.

import type { SeverityName } from "../../ws/errors";

// The MIT-encoding gain range (03 §2.3; LeRobot tables.py MIT_KP_RANGE /
// MIT_KD_RANGE). Fixed and motor-independent. A value outside it is clamped at
// encoding with no error, so the screen refuses the save instead (CG-G-S03c).
export const MIT_KP_RANGE = { min: 0, max: 500 } as const;
export const MIT_KD_RANGE = { min: 0, max: 5 } as const;

// The POS_FORCE second parameter is a per-unit current limit in [0,1] (03 §2.10),
// NOT a torque in Nm. pu↔N is unmeasured, so the screen exposes torque_pu as the
// first-class parameter and never labels a grasp force in N/Nm (CG-G-S03a).
export const GRIPPER_TORQUE_PU_RANGE = { min: 0, max: 1 } as const;
export const TORQUE_PU_LABEL = "torque_pu (per-unit)";

// The Damiao feedback ERR nibble set (03 §2.7, 14 §2.4). Nibble 0 = disable,
// 1 = enable (normal); 8..E are the seven faults the motor-error view renders.
// Only the nibble→OA-MOT-code identity is mirrored here (it is protocol structure,
// like the frozen frame-type set in ws/envelope). The human message + recovery
// hint are NOT mirrored — they come from the CTR-ERR registry at runtime and are
// never duplicated in the browser (CG-G-S03g).
export const MOT_DISABLE_NIBBLE = "0";
export const MOT_ENABLE_NIBBLE = "1";
export const MOT_FAULT_NIBBLES = ["8", "9", "A", "B", "C", "D", "E"] as const;
export type MotFaultNibble = (typeof MOT_FAULT_NIBBLES)[number];

export type MotorTypeName = "DM4310" | "DM4340" | "DM8009" | "DM3507";

// One motor's identity as the backend RID read (WP-0B-07) reports it. PMAX/VMAX/
// TMAX are the motor's internal scale limits (RID 21/22/23); the screen renders
// them, it does not derive them.
export interface MotorDescriptor {
  jointName: string;
  motorType: MotorTypeName;
  // Damiao send / feedback CAN ids (03 §2.1). Rendered as the CAN-ID map.
  sendCanId: number;
  recvCanId: number;
  pMaxRad: number;
  vMaxRadS: number;
  tMaxNm: number;
}

// A joint angle band in radians. Backend frame (F_URDF user coordinates, 03 §2.9);
// the browser never converts units or frames (CTR-UNIT@v1 is backend-owned).
export interface JointLimitRad {
  lo: number;
  hi: number;
}

// A named gain/limit profile (03 §2.8 — five real sets; the active one is
// backend-selected). The screen renders the list, shows which is active, and lets
// the operator edit + submit a save intent; it owns none of the values.
export interface GainLimitProfile {
  name: string;
  kp: readonly number[];
  kd: readonly number[];
  operationalLimitsRad: readonly JointLimitRad[];
}

// Per-motor live state carried IN the WS state frame (03 §2.6). There is no
// separate temperature poll (CG-G-S03b): T_MOS = driver MOSFET temp, T_Rotor =
// coil temp (°C integers); errNibble is the ERR nibble the backend extracted from
// feedback data[0], which upstream MotorState drops (14 FR-OPS-018).
export interface MotorRuntimeState {
  jointName: string;
  tempMosC: number;
  tempRotorC: number;
  errNibble: string;
}

// The gripper's POS_FORCE + endpoint-capture state (03 §2.10, WP-2A-08).
export interface GripperState {
  // Per-unit current limit [0,1]. NOT Nm.
  torquePu: number;
  // The configured POS_FORCE max speed (rad/s) from backend config. It may exceed
  // the motor's physical vMax; the screen shows the reachable value, never this
  // raw figure (03 §2.10 note — 50 rad/s > DM4310 vMax).
  configuredSpeedRadS: number;
  // The gripper motor's (J8) physical vMax (rad/s), from its own descriptor.
  motorVMaxRadS: number;
  // Native rad captured at the physical open/close ends, or null until captured.
  // norm∈[0,1] is the backend's linear interpolation between them (03 §2.10); the
  // screen renders capture state and sends the capture intent only.
  openRad: number | null;
  closeRad: number | null;
}

// One CTR-ERR registry row as the backend serves it. The screen looks its seven
// MOT fault codes up here and never hardcodes the hint text.
export interface ErrorRegistryEntry {
  message: string;
  recoveryHint: string;
  severity: SeverityName;
}

// Everything the screen renders, sourced from the backend. Empty/null fields mean
// "the backend has not delivered this yet" and are shown as unavailable, never
// fabricated (control stays blocked while unloaded — CG-G-S03e).
export interface MotorSetupSource {
  motors: readonly MotorDescriptor[];
  // Mechanical hard-stop limits (URDF v2, backend-owned). The subset guard for a
  // save reads these; the screen does not know them a priori.
  mechanicalLimitsRad: readonly JointLimitRad[];
  profiles: readonly GainLimitProfile[];
  activeProfileName: string | null;
  motorStates: readonly MotorRuntimeState[];
  gripper: GripperState | null;
  errorRegistry: Readonly<Record<string, ErrorRegistryEntry>>;
}

// A profile edit the operator submits. The screen guards it before it ever reaches
// the sink.
export interface ProfileSaveDraft {
  name: string;
  kp: readonly number[];
  kd: readonly number[];
  operationalLimitsRad: readonly JointLimitRad[];
}

// The intent sink — the only way the screen affects the robot, all through the
// single backend gateway. There is no CAN, no clamp, no conversion here.
export interface MotorSetupSink {
  loadProfile(name: string): void;
  saveProfile(draft: ProfileSaveDraft): void;
  captureGripperEndpoint(which: "open" | "close"): void;
}

export function kpInRange(kp: number): boolean {
  return kp >= MIT_KP_RANGE.min && kp <= MIT_KP_RANGE.max;
}

export function kdInRange(kd: number): boolean {
  return kd >= MIT_KD_RANGE.min && kd <= MIT_KD_RANGE.max;
}

export function torquePuInRange(pu: number): boolean {
  return pu >= GRIPPER_TORQUE_PU_RANGE.min && pu <= GRIPPER_TORQUE_PU_RANGE.max;
}

// op ⊆ mech per joint: the operational band must sit inside the mechanical
// hard-stop band (CG-G-S03d). A validity guard against the backend's own
// mechanical set, not a re-derivation of a clamp.
export function limitIsSubset(op: JointLimitRad, mech: JointLimitRad): boolean {
  return op.lo >= mech.lo && op.hi <= mech.hi && op.lo <= op.hi;
}

export interface ProfileValidation {
  ok: boolean;
  reasons: string[];
}

// Refuse a save whose gains leave the MIT range (CG-G-S03c) or whose operational
// limits are not a subset of the mechanical limits (CG-G-S03d). Returns every
// reason so the operator sees all of them at once, not just the first.
export function validateProfileSave(
  draft: ProfileSaveDraft,
  mechanicalLimitsRad: readonly JointLimitRad[],
): ProfileValidation {
  const reasons: string[] = [];
  draft.kp.forEach((kp, index) => {
    if (!kpInRange(kp)) {
      reasons.push(`J${index + 1} kp ${kp} ∉ [${MIT_KP_RANGE.min}, ${MIT_KP_RANGE.max}]`);
    }
  });
  draft.kd.forEach((kd, index) => {
    if (!kdInRange(kd)) {
      reasons.push(`J${index + 1} kd ${kd} ∉ [${MIT_KD_RANGE.min}, ${MIT_KD_RANGE.max}]`);
    }
  });
  draft.operationalLimitsRad.forEach((op, index) => {
    const mech = mechanicalLimitsRad[index];
    if (!mech) {
      reasons.push(`J${index + 1} 기계 리밋 미제공 (mechanical limit unavailable)`);
      return;
    }
    if (!limitIsSubset(op, mech)) {
      reasons.push(
        `J${index + 1} 운영 리밋 [${op.lo}, ${op.hi}] ⊄ 기계 리밋 [${mech.lo}, ${mech.hi}]`,
      );
    }
  });
  return { ok: reasons.length === 0, reasons };
}

// The physically reachable gripper speed. The motor cannot exceed its own vMax, so
// the screen shows min(configured, vMax) and never the misleading raw config value
// (03 §2.10; CG-G-S03f). Display-only — the backend owns the encoded command, and
// vMax comes from the injected descriptor, never a literal here.
export function effectiveGripperSpeedRadS(
  configuredRadS: number,
  motorVMaxRadS: number,
): number {
  return Math.min(configuredRadS, motorVMaxRadS);
}

export function gripperSpeedExceedsVMax(
  configuredRadS: number,
  motorVMaxRadS: number,
): boolean {
  return configuredRadS > motorVMaxRadS;
}

// nibble → OA-MOT code, mirroring the frozen damiao_err_nibble_map (14 §2.4). Only
// the seven fault nibbles map; 0/1 are normal states with no fault code.
export function motErrCodeForNibble(nibble: string): string | null {
  const upper = nibble.toUpperCase();
  if (!(MOT_FAULT_NIBBLES as readonly string[]).includes(upper)) {
    return null;
  }
  return `OA-MOT-00${upper}`;
}

export function isFaultNibble(nibble: string): boolean {
  return (MOT_FAULT_NIBBLES as readonly string[]).includes(nibble.toUpperCase());
}

export interface MotErrReferenceEntry {
  nibble: string;
  code: string;
  message: string;
  recoveryHint: string;
  severity: SeverityName;
}

// Build the seven-row motor-error reference from the injected CTR-ERR registry. The
// nibble→code identity is the frozen mirror; the message + recovery hint are read
// from the registry (reuse, never duplicate — CG-G-S03g). A code the registry
// omits is surfaced honestly rather than invented.
export function motErrReference(
  registry: Readonly<Record<string, ErrorRegistryEntry>>,
): MotErrReferenceEntry[] {
  return MOT_FAULT_NIBBLES.map((nibble) => {
    const code = `OA-MOT-00${nibble}`;
    const entry = registry[code];
    return {
      nibble,
      code,
      message: entry ? entry.message : "(레지스트리 미제공)",
      recoveryHint: entry ? entry.recoveryHint : "(복구 힌트 미제공)",
      severity: entry ? entry.severity : "ERROR",
    };
  });
}

// Control may only begin once a gain/limit profile is loaded (CG-G-S03e): with no
// profile the physical stiffness is undefined and must not be commanded.
export function controlAllowed(activeProfileName: string | null): boolean {
  return activeProfileName !== null;
}

// Extract the MOT-relevant per-motor state from a decoded WS state-frame body. The
// state frame is the ONLY source of temperature and err nibble (CG-G-S03b: no
// polling); this is parse-only and issues no request. A missing field is left as
// NaN / disable rather than fabricated as a plausible number.
export function parseMotorStatesFromFrame(
  body: Record<string, unknown>,
): MotorRuntimeState[] {
  const raw = body["motor_states"];
  if (!Array.isArray(raw)) {
    return [];
  }
  const states: MotorRuntimeState[] = [];
  for (const item of raw) {
    if (typeof item !== "object" || item === null) {
      continue;
    }
    const record = item as Record<string, unknown>;
    states.push({
      jointName: typeof record.joint_name === "string" ? record.joint_name : "",
      tempMosC: typeof record.temp_mos_c === "number" ? record.temp_mos_c : NaN,
      tempRotorC: typeof record.temp_rotor_c === "number" ? record.temp_rotor_c : NaN,
      errNibble: typeof record.err_nibble === "string" ? record.err_nibble : MOT_DISABLE_NIBBLE,
    });
  }
  return states;
}
