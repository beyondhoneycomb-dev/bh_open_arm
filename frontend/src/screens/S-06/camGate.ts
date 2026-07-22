// PG-CAM-001 / PG-DEPTH-001 gate disposition for a tile (graceful 3C-gate render).
//
// These are HARDWARE gates (WP-3C-01) that are NOT built yet, so their result
// arrives as WS state that is currently "pending". The screen RENDERS that state
// — a pending/reduced badge — and never fabricates a verdict or blocks on a gate
// that has not landed (02d graceful-3C rule; 02d §2.2 WP-G-S06 negative branch).
// When a real verdict does arrive:
//   - PG-CAM-001 DEGRADED_ACCEPTED blocks the offending config tile and shows a
//     standing reduced note; other tiles render normally.
//   - PG-DEPTH-001 failure forces RGB-only: the depth tile, its colormap, and the
//     frustum depth layer are removed.
// A pending gate removes nothing and blocks nothing — that is the whole point.

// The gate verdicts the screen may receive. "pending" is the not-yet-landed
// hardware state; the screen must render it without inventing a pass or fail.
export type GateOutcome = "pending" | "pass" | "degraded_accepted" | "fail_blocking";

export interface CameraGateState {
  // PG-CAM-001 (camera capability: format/topology/sync/drop).
  pgCam001: GateOutcome;
  // PG-DEPTH-001 (RealSense depth actually works on LeRobot v0.6.0).
  pgDepth001: GateOutcome;
  // The slots PG-CAM-001 degraded → their config tile is blocked (reduced note).
  blockedSlots: readonly string[];
}

export type TileDisposition = "normal" | "pending" | "blocked";

export interface TileGateView {
  disposition: TileDisposition;
  // The standing note shown for a pending or blocked tile; null when normal.
  note: string | null;
}

export const PG_CAM_PENDING_NOTE = "PG-CAM-001 미착지 — 구성 검증 대기(하드웨어 게이트)";
export const PG_CAM_BLOCKED_NOTE = "PG-CAM-001 DEGRADED_ACCEPTED — 이 구성 차단(축소)";
export const PG_DEPTH_PENDING_NOTE = "PG-DEPTH-001 미착지 — 뎁스 실동작 미검증";
export const PG_DEPTH_REDUCED_NOTE = "PG-DEPTH-001 실패 — RGB-only 축소(뎁스 레이어 제거)";

// The disposition of one tile under the current gate state. A degraded PG-CAM-001
// blocks exactly the listed slots; a pending gate marks the tile pending but
// leaves it rendered; anything else is normal.
export function tileGate(slot: string, gates: CameraGateState): TileGateView {
  if (gates.pgCam001 === "degraded_accepted" && gates.blockedSlots.includes(slot)) {
    return { disposition: "blocked", note: PG_CAM_BLOCKED_NOTE };
  }
  if (gates.pgCam001 === "pending") {
    return { disposition: "pending", note: PG_CAM_PENDING_NOTE };
  }
  return { disposition: "normal", note: null };
}

// Whether the depth layer (depth tile, colormap, frustum depth) is rendered at
// all. RGB-only reduction removes it on an actual PG-DEPTH-001 failure; a pending
// gate keeps depth visible (with its own pending note) rather than fabricating a
// reduction the hardware never reported.
export function depthLayerEnabled(gates: CameraGateState): boolean {
  return gates.pgDepth001 !== "fail_blocking" && gates.pgDepth001 !== "degraded_accepted";
}

// The standing depth note, or null when depth is fully verified. Pending and
// reduced are distinct so an operator can tell "not checked yet" from "checked,
// removed".
export function depthNote(gates: CameraGateState): string | null {
  if (!depthLayerEnabled(gates)) {
    return PG_DEPTH_REDUCED_NOTE;
  }
  if (gates.pgDepth001 === "pending") {
    return PG_DEPTH_PENDING_NOTE;
  }
  return null;
}
