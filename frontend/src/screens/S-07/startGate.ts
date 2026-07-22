// The session-start gate (CG-G-S07f, CG-G-S07g). All three predicates reuse the
// WP-G-03 global surface rather than re-deciding anything: the six-item preflight
// (canStartSession), the one-hour disk-headroom floor (DISK_MIN_HEADROOM_HOURS),
// and the push_to_hub confirm requirement (pushToHubRequiresConfirm). The screen is
// a facade — it composes these backend/global decisions, it does not invent them.

import {
  canStartSession,
  DISK_MIN_HEADROOM_HOURS,
  pushToHubRequiresConfirm,
  type PreflightItem,
  type PushToHubState,
} from "../../global";
import type { StoragePrediction } from "./types";

// Whether the disk prediction leaves at least one hour of recordable headroom.
// Below this the collection start is hard-blocked (CG-G-S07g).
export function storageHeadroomOk(storage: StoragePrediction): boolean {
  return storage.headroomHours >= DISK_MIN_HEADROOM_HOURS;
}

// The start is BLOCKED when the preflight is incomplete/failing OR disk headroom is
// under one hour. push_to_hub does NOT block here — it gates behind an explicit
// confirm (CG-G-S07f), which is a separate step, not a block.
export function startBlocked(
  preflight: readonly PreflightItem[],
  storage: StoragePrediction,
): boolean {
  return !canStartSession(preflight) || !storageHeadroomOk(storage);
}

// Whether starting must first pass the explicit push_to_hub upload confirmation,
// consistent with the WP-G-03 badge (CG-G-S07f).
export function needsPushToHubConfirm(pushToHub: PushToHubState): boolean {
  return pushToHubRequiresConfirm(pushToHub);
}
