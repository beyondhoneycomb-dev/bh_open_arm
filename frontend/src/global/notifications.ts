// The notification/alert center model (FR-GUI-066). Each notification carries a
// CTR-ERR severity and an OA-* code. The load-bearing rule (CG-G-03g): a
// notification at ERROR or above keeps the badge held until the operator
// acknowledges it — acking is the only thing that clears the hold, never a
// timeout. Severity and the hold threshold come from the frozen CTR-ERR mirror,
// so "ERROR and above" is defined by the contract, not re-decided here.

import { holdsBadgeUntilAck, type SeverityValue } from "./contracts/errorCodes";

export interface Notification {
  id: string;
  // OA-* code from CTR-ERR; the backend owns the code table.
  code: string;
  severity: SeverityValue;
  // Emitting subsystem, e.g. "OA-CAN" domain source or a screen name.
  source: string;
  // Epoch milliseconds the notification was raised.
  timestamp: number;
  detail: string;
  acked: boolean;
}

// Notifications that hold the badge: severity ERROR or above and not yet acked.
export function heldNotifications(notifications: readonly Notification[]): Notification[] {
  return notifications.filter((n) => holdsBadgeUntilAck(n.severity) && !n.acked);
}

// CG-G-03g: whether the badge must stay visible. True while any ERROR+ alert is
// unacknowledged.
export function badgeIsHeld(notifications: readonly Notification[]): boolean {
  return heldNotifications(notifications).length > 0;
}

// The count shown on the badge — unacknowledged ERROR+ alerts.
export function heldCount(notifications: readonly Notification[]): number {
  return heldNotifications(notifications).length;
}

// Acknowledge one notification, returning a new list. Only acking flips the flag;
// nothing here expires a notification on its own.
export function acknowledge(
  notifications: readonly Notification[],
  id: string,
): Notification[] {
  return notifications.map((n) => (n.id === id ? { ...n, acked: true } : n));
}
