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

export interface RobotBadgeState {
  connected: boolean;
  mode: LiveLinkMode;
  // Active gain/limit profile name, or null when none is loaded (control blocked).
  profileName: string | null;
  // Label of the control holder (session), or null when nobody holds control.
  controlHolder: string | null;
}

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

      <span className="oa-badge oa-badge--nominal" data-badge="mode">
        <span className="oa-badge__key">모드</span>
        <span className="oa-badge__value">{robot.mode}</span>
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

      <VelocityTorqueBadge state={velocityTorque} onToggle={onToggleVelocityTorque} />
      <PushToHubBadge state={pushToHub} />
      <NotificationBadge notifications={notifications} />
    </div>
  );
}
