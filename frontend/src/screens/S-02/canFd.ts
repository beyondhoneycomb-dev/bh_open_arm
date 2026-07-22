// CAN-FD startup gate for S-02 (CG-G-S02e, FR-GUI-112, 02 F-7'). CAN-FD (nominal
// 1 Mbps / data 5 Mbps) is an `ip link` fact python-can cannot set, so the GUI
// VERIFIES it and blocks startup while it is unverified. The verification itself
// lives in the WP-G-03 foundation (canStartupBlockers / CAN_FD_* bitrates); this
// module only FOLDS that per-interface check across every CAN interface the
// connection uses, so S-02 states no second CAN-FD value of its own.

import { canStartupBlockers, type CanInterfaceStatus } from "../../global";

// Every startup blocker across all interfaces, in interface order. Empty only when
// every interface has CAN-FD verified — the condition for startup to be allowed.
export function canStartupBlockersAll(
  interfaces: readonly CanInterfaceStatus[],
): string[] {
  return interfaces.flatMap((iface) => canStartupBlockers(iface));
}

// CG-G-S02e: startup is blocked while any interface has CAN-FD unverified. A
// connection with no interfaces at all is also blocked — "nothing to verify" is
// not "verified".
export function startupBlockedByCan(
  interfaces: readonly CanInterfaceStatus[],
): boolean {
  if (interfaces.length === 0) {
    return true;
  }
  return canStartupBlockersAll(interfaces).length > 0;
}
