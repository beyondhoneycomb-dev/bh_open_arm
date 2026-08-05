// The always-on status badge bar (FR-GUI-060/061/072/073). It shows, on every
// screen: connection, current mode, active gain/limit profile, control holder,
// per-interface CAN state (with intruder PIDs), the two config-flag badges
// (use_velocity_and_torque, push_to_hub), and the unacknowledged-alert badge.
// The bar only observes and renders; the stop controls and the alert center are
// separate elements composed alongside it by GlobalSafetyBar.

import { CanBadge } from "./CanBadge";
import { NotificationBadge } from "./NotificationCenter";
import { PushToHubBadge } from "./PushToHubBadge";
import { VelocityTorqueBadge } from "./VelocityTorqueBadge";
import type { CanInterfaceStatus } from "./canStatus";
import type { PushToHubState, VelocityTorqueState } from "./flags";
import type { LiveLinkMode } from "./modes";
import type { Notification } from "./notifications";

// Every field here has an honest reading for "no session", because this bar renders
// before anything is connected and a badge that claims a healthy state it never
// observed is the failure this shape exists to prevent.
export interface RobotBadgeState {
  connected: boolean;
  // Null until a session reports a mode. IDLE is not that value — IDLE is a state a
  // connected robot holds, so using it here would claim a connection.
  mode: LiveLinkMode | null;
  // Active gain/limit profile name, or null when none is loaded (control blocked).
  profileName: string | null;
  // Label of the control holder (session), or null when nobody holds control.
  controlHolder: string | null;
}

// Shown where a session has reported no value at all.
export const UNOBSERVED_LABEL = "미상";

// Shown in place of the per-interface CAN badges when the backend has reported no
// interface status. Zero badges would read as "no problem found" when the truth is
// "nothing was looked at" (FR-GUI-061).
export const CAN_UNOBSERVED_LABEL = "관측 없음";

export interface StatusBadgeBarProps {
  robot: RobotBadgeState;
  canInterfaces: readonly CanInterfaceStatus[];
  velocityTorque: VelocityTorqueState;
  pushToHub: PushToHubState;
  notifications: readonly Notification[];
  onToggleVelocityTorque: (enabled: boolean) => void;
}

export function StatusBadgeBar({
  robot,
  canInterfaces,
  velocityTorque,
  pushToHub,
  notifications,
  onToggleVelocityTorque,
}: StatusBadgeBarProps) {
  return (
    <div className="oa-badge-bar" role="status" aria-label="상태 배지">
      <span
        className={`oa-badge ${robot.connected ? "oa-badge--nominal" : "oa-badge--muted"}`}
        data-badge="connection"
      >
        <span className="oa-badge__key">연결</span>
        <span className="oa-badge__value">{robot.connected ? "연결됨" : "끊김"}</span>
      </span>

      <span
        className={`oa-badge ${robot.mode ? "oa-badge--nominal" : "oa-badge--muted"}`}
        data-badge="mode"
      >
        <span className="oa-badge__key">모드</span>
        <span className="oa-badge__value">{robot.mode ?? UNOBSERVED_LABEL}</span>
      </span>

      <span
        className={`oa-badge ${robot.profileName ? "oa-badge--nominal" : "oa-badge--warning"}`}
        data-badge="profile"
      >
        <span className="oa-badge__key">프로파일</span>
        <span className="oa-badge__value">{robot.profileName ?? "미로드"}</span>
      </span>

      <span className="oa-badge oa-badge--muted" data-badge="control-holder">
        <span className="oa-badge__key">제어권</span>
        <span className="oa-badge__value">{robot.controlHolder ?? "없음"}</span>
      </span>

      {canInterfaces.map((iface) => (
        <CanBadge key={iface.iface} status={iface} />
      ))}

      {canInterfaces.length === 0 && (
        <span className="oa-badge oa-badge--muted" data-badge="can-unobserved">
          <span className="oa-badge__key">CAN</span>
          <span className="oa-badge__value">{CAN_UNOBSERVED_LABEL}</span>
        </span>
      )}

      <VelocityTorqueBadge state={velocityTorque} onToggle={onToggleVelocityTorque} />
      <PushToHubBadge state={pushToHub} />
      <NotificationBadge notifications={notifications} />
    </div>
  );
}
