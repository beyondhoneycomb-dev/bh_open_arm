// The notification center (FR-GUI-066) and its always-on badge. The badge stays
// held while any ERROR+ alert is unacknowledged (CG-G-03g); acking is the only
// control that clears it. The center lists notifications newest first with their
// severity, code, source and time, and an ack button per unacked entry.

import {
  badgeIsHeld,
  heldCount,
  type Notification,
} from "./notifications";
import { SEVERITY_NAMES, type SeverityValue } from "./contracts/errorCodes";

function severityName(severity: SeverityValue): string {
  return SEVERITY_NAMES[severity] ?? "UNKNOWN";
}

export interface NotificationBadgeProps {
  notifications: readonly Notification[];
}

// The compact badge shown in the always-on bar.
export function NotificationBadge({ notifications }: NotificationBadgeProps) {
  const held = badgeIsHeld(notifications);
  const count = heldCount(notifications);
  return (
    <span
      className={`oa-badge ${held ? "oa-badge--danger" : "oa-badge--muted"}`}
      data-alert-held={held}
      role="status"
      aria-label={held ? `미확인 경고 ${count}건` : "경고 없음"}
    >
      <span className="oa-badge__key">경고</span>
      <span className="oa-badge__value">{count}</span>
    </span>
  );
}

export interface NotificationCenterProps {
  notifications: readonly Notification[];
  onAck: (id: string) => void;
}

export function NotificationCenter({ notifications, onAck }: NotificationCenterProps) {
  const ordered = [...notifications].sort((a, b) => b.timestamp - a.timestamp);
  return (
    <section className="oa-notifications" aria-label="알림 센터">
      {ordered.length === 0 && (
        <p className="oa-notifications__empty" role="status">
          알림 없음
        </p>
      )}
      <ul className="oa-notifications__list">
        {ordered.map((n) => (
          <li
            key={n.id}
            className={`oa-notification oa-notification--${severityName(n.severity).toLowerCase()}`}
            data-acked={n.acked}
            data-severity={severityName(n.severity)}
          >
            <span className="oa-notification__code">{n.code}</span>
            <span className="oa-notification__severity">{severityName(n.severity)}</span>
            <span className="oa-notification__source">{n.source}</span>
            <span className="oa-notification__detail">{n.detail}</span>
            {!n.acked && (
              <button
                type="button"
                className="oa-notification__ack"
                onClick={() => onAck(n.id)}
              >
                확인
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
