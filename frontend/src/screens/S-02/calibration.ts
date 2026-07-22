// CTR-CAL@v1 calibration record, RENDER ONLY (WP-G-S02 contract). The calibration
// canon is CTR-CAL@v1, owned by WP-1-02: this screen displays its fields and never
// computes, edits or re-derives them. The field set mirrors the frozen schema
// (01 §6.2 CTR-CAL@v1): signs, gripper open/close in radians, captured flag,
// timestamps, zero_method, urdf_zero_offset, motor_zero_raw. Angles are radians;
// the browser does not convert (CTR-UNIT@v1). This module holds only the shape and
// a label map — no logic, because logic would be a second source of truth.

// The zero-establishing procedure that produced this calibration (02 §2.0.2
// FR-CON-031). The same joint angle means a different physical pose per method, so
// the method is part of the record and must be shown, not assumed.
export const ZERO_METHODS = ["lerobot_hanging", "enactic_jig", "enactic_bumping"] as const;
export type ZeroMethod = (typeof ZERO_METHODS)[number];

export interface CalibrationRecord {
  // Per-joint direction sign (+1/-1), keyed by URDF joint name.
  signs: Readonly<Record<string, number>>;
  // Gripper open/close positions in radians.
  gripperOpenRad: number;
  gripperCloseRad: number;
  // Whether the zero was captured this session.
  captured: boolean;
  // ISO-8601 timestamps the backend stamped.
  capturedAt: string | null;
  updatedAt: string | null;
  zeroMethod: ZeroMethod;
  // URDF zero offset in radians, keyed by URDF joint name.
  urdfZeroOffsetRad: Readonly<Record<string, number>>;
  // Raw motor zero readings (0xFE readback), keyed by URDF joint name.
  motorZeroRaw: Readonly<Record<string, number>>;
}

export const ZERO_METHOD_LABELS: Record<ZeroMethod, string> = {
  lerobot_hanging: "LeRobot hanging (팔 늘어뜨림 + 그리퍼 닫음)",
  enactic_jig: "enactic 지그 (Zero-Position Calibration Jig)",
  enactic_bumping: "enactic 하드스톱 범핑",
};
