// The eight LiveLinkModes the GUI ranges over (FR-GUI-080) and the machinery to
// enumerate the full screen x mode x role matrix the E-Stop must be reachable
// across (CG-G-03b). The screen axis is drawn from the canonical route registry
// (WP-G-00) rather than re-listed here, so the matrix can never drift from the 13
// screens of 13 §2.6. WP-G-03 owns only the safety reading of this matrix; the
// mode/role table itself (rights per mode) is WP-G-04's deliverable.

import { SCREENS, type ScreenId } from "../routes/registry";
import { CONTROL_ROLES, type ControlRole } from "./contracts/wsRoles";

// The eight modes of FR-GUI-080. IDLE holds no send_action right; MOTOR_SETUP is
// the only mode allowed while CAN is unowned (CLI bring-up). The list is the
// closed set the safety matrix iterates.
export const LIVE_LINK_MODES = [
  "IDLE",
  "MANUAL",
  "TELEOP_VR",
  "TELEOP_KER",
  "RECORD",
  "INFERENCE",
  "SIM",
  "MOTOR_SETUP",
] as const;

export type LiveLinkMode = (typeof LIVE_LINK_MODES)[number];

// One cell of the reachability matrix: a screen the operator is on, the active
// mode, and whether this client holds control.
export interface SafetyContext {
  screen: ScreenId;
  mode: LiveLinkMode;
  role: ControlRole;
}

// Every (screen, mode, role) combination — 13 x 8 x 2. The E-Stop acceptance
// check (CG-G-03b) asserts the control is reachable in each one.
export function estopMatrix(): SafetyContext[] {
  const cells: SafetyContext[] = [];
  for (const screen of SCREENS) {
    for (const mode of LIVE_LINK_MODES) {
      for (const role of CONTROL_ROLES) {
        cells.push({ screen: screen.id, mode, role });
      }
    }
  }
  return cells;
}

export const ESTOP_MATRIX_SIZE = SCREENS.length * LIVE_LINK_MODES.length * CONTROL_ROLES.length;
