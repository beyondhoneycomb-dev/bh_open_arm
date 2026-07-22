// The backend-derived inputs S-02 renders from, plus an offline default fixture.
// S-02 is a window onto the CON domain (02): every number here — the CAN interface
// status, the discovered motors, the URDF joint names and rest pose, the live
// telemetry pose, the profiles, the CTR-CAL@v1 calibration — originates in the
// backend (WP-1-02, WP-0B-02, WP-0B-05). This module names that bundle and gives
// an honest offline default: CAN-FD unverified, no telemetry, no calibration, so
// the screen reads "not ready" rather than "fine" before a backend connects (the
// WP is AI-offline; the GUI is verified against fixtures, never real hardware).

import { CAN_FD_NOMINAL_BITRATE, CAN_FD_DATA_BITRATE, type CanInterfaceStatus } from "../../global";
import type { CalibrationRecord } from "./calibration";

// One USB-CAN adapter channel as the hardware inventory shows it (02 §2.1). The
// adapter facts (serial, driver, firmware) are read by the backend; rendered here.
export interface HardwareAdapter {
  id: string;
  label: string;
  // The fixed udev name of the channel (WP-0B-05, e.g. oa_fl/oa_fr/oa_ll/oa_lr).
  udevName: string;
  iface: string;
  driver: string;
  firmware: string;
}

// A motor the first-connect wizard's bus scan discovered (02 §2.9 discover). The
// type/limits are the backend's RID readback; the screen only compares/renders.
export interface DiscoveredMotor {
  canId: number;
  motorType: string;
  side: "left" | "right";
  jointName: string;
  // Error nibble decoded by the backend, or null when clear.
  errorCode: string | null;
}

// A robot profile (02 §2 import/export): a named side + CAN-id map + motor types.
// Selected by the operator; never edited here (that is S-03's motor-config screen).
export interface RobotProfile {
  name: string;
  side: "left" | "right" | "bimanual";
}

export interface ConnectionSource {
  // Per-interface CAN status from the WP-G-03 detectors (flock/intruder/link/FD).
  readonly canInterfaces: readonly CanInterfaceStatus[];
  // The hardware inventory (adapters/channels) the backend enumerated.
  readonly adapters: readonly HardwareAdapter[];
  // Motors the bus scan discovered, empty before a scan runs.
  readonly discoveredMotors: readonly DiscoveredMotor[];
  // The URDF joint-name set for the connection (reference set for the delta view).
  readonly jointNames: readonly string[];
  // The URDF rest pose in radians — the zero the operator aligns to.
  readonly restPositionsRad: Readonly<Record<string, number>>;
  // The live telemetry pose in radians, or null before any frame arrives.
  readonly currentPositionsRad: Readonly<Record<string, number>> | null;
  // Selectable robot profiles.
  readonly profiles: readonly RobotProfile[];
  // The persisted CTR-CAL@v1 calibration record, or null when uncalibrated.
  readonly calibration: CalibrationRecord | null;
  // Injectable monotonic clock reading (ms) for deterministic audit timestamps.
  readonly nowMonoMs: number;
}

const DEMO_SIDES = ["left", "right"] as const;
const JOINTS_PER_ARM = 7;

function demoJointNames(): string[] {
  return DEMO_SIDES.flatMap((side) =>
    Array.from({ length: JOINTS_PER_ARM }, (_unused, index) => `openarm_${side}_joint${index + 1}`),
  );
}

function demoRestPose(jointNames: readonly string[]): Record<string, number> {
  // URDF rest zero is all-joints-zero radians; the honest rest reference pose.
  return Object.fromEntries(jointNames.map((name) => [name, 0]));
}

function demoInterface(
  iface: string,
  canFdConfigured: boolean,
): CanInterfaceStatus {
  return {
    iface,
    flockHeld: false,
    boundSocketCount: 0,
    intruderPids: [],
    linkState: "ERROR-ACTIVE",
    canFdConfigured,
  };
}

function demoAdapters(): HardwareAdapter[] {
  return [
    {
      id: "adapter-0",
      label: "USB-CAN 어댑터 0",
      udevName: "oa_fl",
      iface: "can0",
      driver: "gs_usb",
      firmware: "candleLight fw",
    },
    {
      id: "adapter-1",
      label: "USB-CAN 어댑터 1",
      udevName: "oa_fr",
      iface: "can1",
      driver: "gs_usb",
      firmware: "candleLight fw",
    },
  ];
}

// The offline default. CAN-FD is unverified on both interfaces, there is no
// telemetry and no calibration — so every S-02 gate reads its blocking state until
// a real backend supplies verified facts.
export function defaultConnectionSource(): ConnectionSource {
  const jointNames = demoJointNames();
  return {
    canInterfaces: [demoInterface("can0", false), demoInterface("can1", false)],
    adapters: demoAdapters(),
    discoveredMotors: [],
    jointNames,
    restPositionsRad: demoRestPose(jointNames),
    currentPositionsRad: null,
    profiles: [
      { name: "openarm_left_v2", side: "left" },
      { name: "openarm_right_v2", side: "right" },
      { name: "openarm_bimanual_v2", side: "bimanual" },
    ],
    calibration: null,
    nowMonoMs: 0,
  };
}

// Re-export the frozen CAN-FD bitrates so views render the required values from
// one place (the foundation), never a literal typed into S-02.
export { CAN_FD_NOMINAL_BITRATE, CAN_FD_DATA_BITRATE };
