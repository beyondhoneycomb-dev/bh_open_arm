// The notification/alert center model (FR-GUI-066).
//
// What holds the badge is whether the notification STOPPED something, not how its
// severity sorts. A held alert is one the operator has to clear before the thing it
// stopped can resume — the latch, the blocked control, the refused start — and acking
// is the only thing that clears it, never a timeout.
//
// Severity is a label on the row, not an input to that decision. It used to be one: the
// rule read "ERROR or above" and the code implemented it as `severity >= ERROR`, which
// silently swept in `STALE`. `STALE` is not a worse fault than `ERROR` — it is the
// answer "we could not check", sitting on a different axis that happens to be numbered
// above it (`CTR-ERR`, 14 §2.10). Ordering the two and then thresholding produced a
// verdict nobody chose. There is no threshold here now, so there is nothing to order.

import type { SeverityValue } from "./contracts/errorCodes";

export interface Notification {
  id: string;
  // OA-* code from CTR-ERR; the backend owns the code table.
  code: string;
  // Shown on the row so a person can read what kind of fault this was. Nothing in this
  // module branches on it.
  severity: SeverityValue;
  // Emitting subsystem, e.g. "OA-CAN" domain source or a screen name.
  source: string;
  // Epoch milliseconds the notification was raised.
  timestamp: number;
  detail: string;
  // Something is held because of this — a latch engaged, a control refused, a start
  // blocked — and it stays held until this is acked. The emitter sets it, because only
  // the emitter knows whether anything actually stopped.
  blocking: boolean;
  acked: boolean;
}

// Notifications that hold the badge: something is still stopped and nobody has cleared
// it. A non-blocking notification is a log row — it appears in the center and never
// demands a click, which is what keeps the click meaningful.
export function heldNotifications(notifications: readonly Notification[]): Notification[] {
  return notifications.filter((n) => n.blocking && !n.acked);
}

// CG-G-03g: whether the badge must stay visible. True while anything this stopped is
// still unacknowledged.
export function badgeIsHeld(notifications: readonly Notification[]): boolean {
  return heldNotifications(notifications).length > 0;
}

// The count shown on the badge — unacknowledged blocking alerts.
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
