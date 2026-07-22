// The preflight gate (FR-GUI-071, CG-G-03f). Six checks must all pass before a
// data collection or teleop session can start. The gate is hard: there is no
// "warn then proceed" path — a single failed item blocks the start, and a start
// requested with a missing item is treated as a failure, not a pass. Item 1 (CAN)
// subsumes the CAN-FD startup check (CG-G-03h): if CAN-FD is unset the CAN item
// fails and the start is blocked. The item results are produced by the backend
// detectors and screens; this module owns only the closed item set and the gate.

// The six canonical preflight items, in the order FR-GUI-071 lists them.
export const PREFLIGHT_ITEM_IDS = [
  "can",
  "cameras",
  "velocity_torque",
  "calibration",
  "disk",
  "profile",
] as const;

export type PreflightItemId = (typeof PREFLIGHT_ITEM_IDS)[number];

export const PREFLIGHT_ITEM_LABELS: Record<PreflightItemId, string> = {
  can: "CAN 소유권·링크 (CAN-FD 포함)",
  cameras: "카메라 연결·USB 링크 속도",
  velocity_torque: "use_velocity_and_torque = true",
  calibration: "캘리브레이션 유효성",
  disk: "디스크 여유 (≥1시간)",
  profile: "게인/리밋 프로파일 로드",
};

// Minimum recordable headroom on disk: at least one hour of capacity (FR-GUI-071
// item 5 / spec 13 §4.3). Collection start is blocked below this.
export const DISK_MIN_HEADROOM_HOURS = 1;

export interface PreflightItem {
  id: PreflightItemId;
  passed: boolean;
  // Optional human-readable reason, shown when the item fails.
  detail?: string;
}

// Whether the item set is the full canonical six. A start attempt with a missing
// item must not pass by omission, so the gate requires every id to be present.
export function preflightIsComplete(items: readonly PreflightItem[]): boolean {
  const present = new Set(items.map((item) => item.id));
  return PREFLIGHT_ITEM_IDS.every((id) => present.has(id));
}

// The items that failed, in canonical order. Empty only when all six pass.
export function failedPreflightItems(items: readonly PreflightItem[]): PreflightItem[] {
  const byId = new Map(items.map((item) => [item.id, item] as const));
  const failures: PreflightItem[] = [];
  for (const id of PREFLIGHT_ITEM_IDS) {
    const item = byId.get(id);
    // A missing item is a failure, not a pass — the gate never proceeds on
    // incomplete information.
    if (!item || !item.passed) {
      failures.push(item ?? { id, passed: false, detail: "미검사" });
    }
  }
  return failures;
}

// CG-G-03f: collection/teleop may start only when the item set is complete and
// every item passes. There is no override parameter by design.
export function canStartSession(items: readonly PreflightItem[]): boolean {
  return preflightIsComplete(items) && failedPreflightItems(items).length === 0;
}
