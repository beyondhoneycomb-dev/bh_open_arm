// CAN interface status the GUI renders and reasons about (FR-GUI-061/062, spec
// 13 §4.1). SocketCAN gives no exclusive bind (F-1): two processes can bind the
// same interface and the kernel raises nothing, so ownership is something the
// application asserts, not something the OS reports. The GUI therefore shows
// "do we hold the flock lock, and is there an intruder", not "who owns it". The
// three inputs that answer that come from the backend detectors this WP consumes:
// WP-0B-01 (flock lock held), WP-0B-04 (bound-socket count from
// /proc/net/can/raw), WP-0B-03 (intruder PIDs). CAN is always owned by the
// backend process; the browser only observes this over the WS.

// Our backend is the one legitimate binder. More than one bound socket on an
// interface means an intruder is on the bus (F-1 / spec 13 §4.3).
export const BOUND_SOCKET_SOLE_OWNER = 1;

// CAN-FD bitrates the link must carry (FR-GUI-062). python-can's socketcan
// backend ignores these arguments (F-7'), so CAN-FD is an `ip link` fact the GUI
// verifies rather than sets.
export const CAN_FD_NOMINAL_BITRATE = 1_000_000;
export const CAN_FD_DATA_BITRATE = 5_000_000;

// Link controller state from `ip -details link show` (FR-GUI-062). BUS-OFF is a
// fault; the rest are shown but not by themselves control-blocking here.
export type CanLinkState =
  | "ERROR-ACTIVE"
  | "ERROR-WARNING"
  | "ERROR-PASSIVE"
  | "BUS-OFF"
  | "STOPPED"
  | "UNKNOWN";

// The GUI-visible CAN state (spec 13 §4.1). ACQUIRING/READONLY/RELEASING are
// transient phases the backend reports explicitly; the safety-relevant states
// below are derived from the detector inputs.
export type CanState =
  | "UNOWNED"
  | "OWNED"
  | "INTRUDED"
  | "CONFLICT"
  | "FAULT";

export interface CanInterfaceStatus {
  // Interface name, e.g. "can0"/"can1".
  iface: string;
  // WP-0B-01: whether our backend holds the flock lock on this interface.
  flockHeld: boolean;
  // WP-0B-04: bound sockets on this ifindex (/proc/net/can/raw). >1 means an
  // intruder shares the bus.
  boundSocketCount: number;
  // WP-0B-03: PIDs of intruding CAN clients, empty when none detected.
  intruderPids: readonly number[];
  // Link controller state (`ip -details link show`).
  linkState: CanLinkState;
  // Whether CAN-FD is enabled at the `ip link` layer (F-7').
  canFdConfigured: boolean;
}

// Whether an intruder is present on the interface (bound socket beyond the sole
// legitimate owner). This is the condition, per spec 13 §4.1, that separates
// INTRUDED/CONFLICT from OWNED/UNOWNED.
export function hasIntruder(status: CanInterfaceStatus): boolean {
  return status.boundSocketCount > BOUND_SOCKET_SOLE_OWNER;
}

// Derive the GUI CAN state from the detector inputs (spec 13 §4.1). An intruder
// while we hold the lock is INTRUDED; an intruder while we do not is CONFLICT;
// BUS-OFF is FAULT; holding the lock cleanly is OWNED; otherwise UNOWNED.
export function deriveCanState(status: CanInterfaceStatus): CanState {
  if (hasIntruder(status)) {
    return status.flockHeld ? "INTRUDED" : "CONFLICT";
  }
  if (status.linkState === "BUS-OFF") {
    return "FAULT";
  }
  return status.flockHeld ? "OWNED" : "UNOWNED";
}

// CG-G-03e: a bound socket beyond the sole owner blocks the control UI. BUS-OFF
// also blocks control (the bus cannot carry commands).
export function isControlBlocked(status: CanInterfaceStatus): boolean {
  return hasIntruder(status) || status.linkState === "BUS-OFF";
}

// CG-G-03h: CAN-FD not configured at the `ip link` layer blocks startup. Returns
// the reasons this interface blocks startup, empty when it is clear to start.
export function canStartupBlockers(status: CanInterfaceStatus): string[] {
  const blockers: string[] = [];
  if (!status.canFdConfigured) {
    blockers.push(`${status.iface}: CAN-FD 미설정 — ip link로 활성화 필요`);
  }
  return blockers;
}
