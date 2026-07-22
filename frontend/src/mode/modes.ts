// The eight operating modes and who holds send_action() authority in each
// (FR-GUI-080). A mode is a state transition on the ONE backend Robot object in
// the ONE backend process (LiveLinkMode) — never a process restart, never a
// Robot connect()/disconnect() (FR-GUI-081, invariant I-2). connect() calls
// set_zero_position(), which silently invalidates joint limits, virtual walls and
// the dataset frame, so a mode change must move the send_action right, not
// re-open the link (CG-G-04a). This module is the frozen catalog the authority
// table renders; it computes nothing the backend owns — it only names the eight
// modes and the single source that holds send_action in each.
//
// A mode either routes send_action to the real CAN bus (the backend holds the CAN
// lock) or it does not. MOTOR_SETUP is the one mode in which the backend does NOT
// hold the CAN bus, and is therefore the only mode in which an external CAN client
// may run (FR-GUI-086, CG-G-04e). SIM also touches no CAN, but it drives the
// simulated Robot, not an external CLI.

export type ModeId =
  | "IDLE"
  | "MANUAL"
  | "TELEOP_VR"
  | "TELEOP_KER"
  | "RECORD"
  | "INFERENCE"
  | "SIM"
  | "MOTOR_SETUP";

// The kind of source that holds send_action() in a mode. Exactly one source holds
// it at a time — command-source exclusivity (FR-GUI-090), enforced by the backend
// LiveLinkMode mutex, not by this table.
export type AuthorityHolder =
  | "none" // IDLE — no source holds send_action
  | "gui_jog" // MANUAL — the GUI jog panel
  | "teleoperator" // TELEOP_VR / TELEOP_KER / RECORD — a Teleoperator.get_action()
  | "policy" // INFERENCE — a policy action chunk
  | "sim_robot" // SIM — the simulated Robot object
  | "external_cli"; // MOTOR_SETUP — an external CAN CLI, real bus not held

export interface ModeDescriptor {
  id: ModeId;
  // Korean UI label shown in the authority table and badge.
  label: string;
  holder: AuthorityHolder;
  // True for MOTOR_SETUP only: the backend does not hold the CAN bus, so an
  // external CAN client may run (FR-GUI-086, CG-G-04e). Every other mode is false.
  allowsExternalCanClient: boolean;
  // Whether send_action in this mode reaches the real CAN bus. RECORD rides on
  // top of the TELEOP loop, so it drives the real bus; SIM drives the simulated
  // Robot; IDLE and MOTOR_SETUP drive nothing.
  drivesRealBus: boolean;
}

// The eight modes, ordered as FR-GUI-080 lists them. This is the whole authority
// catalog; no mode is added or removed here.
export const MODES: readonly ModeDescriptor[] = [
  {
    id: "IDLE",
    label: "대기 (IDLE)",
    holder: "none",
    allowsExternalCanClient: false,
    drivesRealBus: false,
  },
  {
    id: "MANUAL",
    label: "수동 조작 (MANUAL)",
    holder: "gui_jog",
    allowsExternalCanClient: false,
    drivesRealBus: true,
  },
  {
    id: "TELEOP_VR",
    label: "텔레옵 VR (TELEOP_VR)",
    holder: "teleoperator",
    allowsExternalCanClient: false,
    drivesRealBus: true,
  },
  {
    id: "TELEOP_KER",
    label: "텔레옵 바이래터럴 (TELEOP_KER)",
    holder: "teleoperator",
    allowsExternalCanClient: false,
    drivesRealBus: true,
  },
  {
    id: "RECORD",
    label: "데이터 수집 (RECORD)",
    holder: "teleoperator",
    allowsExternalCanClient: false,
    drivesRealBus: true,
  },
  {
    id: "INFERENCE",
    label: "추론 (INFERENCE)",
    holder: "policy",
    allowsExternalCanClient: false,
    drivesRealBus: true,
  },
  {
    id: "SIM",
    label: "시뮬레이션 (SIM)",
    holder: "sim_robot",
    allowsExternalCanClient: false,
    drivesRealBus: false,
  },
  {
    id: "MOTOR_SETUP",
    label: "모터 설정 (MOTOR_SETUP)",
    holder: "external_cli",
    allowsExternalCanClient: true,
    drivesRealBus: false,
  },
];

// Korean labels for each authority-holder kind, so the badge and table describe
// "who holds send_action" without re-deriving it at each call site.
export const HOLDER_LABELS: Readonly<Record<AuthorityHolder, string>> = {
  none: "권리 없음",
  gui_jog: "GUI 조그",
  teleoperator: "텔레오퍼레이터",
  policy: "정책",
  sim_robot: "시뮬 Robot",
  external_cli: "외부 CAN CLI",
};

export function modeById(id: ModeId): ModeDescriptor {
  const found = MODES.find((mode) => mode.id === id);
  if (!found) {
    throw new Error(`unknown mode id: ${id}`);
  }
  return found;
}

// The single mode that may expose an external CAN client (CG-G-04e). Kept as a
// derived query rather than a hardcoded id so the invariant follows the catalog.
export function externalCanClientModes(): ModeId[] {
  return MODES.filter((mode) => mode.allowsExternalCanClient).map((mode) => mode.id);
}
