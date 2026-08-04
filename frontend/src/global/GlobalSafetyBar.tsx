// The always-on safety surface WP-G-03 delivers, mounted by the shell on every
// screen. It composes the dummy-mode banner, the status badge bar, and the stop
// pair. Its defining property (CG-G-03b): the pair is rendered unconditionally,
// independent of screen, mode, and whether this client holds control, so the
// STOP_HOLD control and the physical-E-Stop guidance are on screen in all 208
// cells of the matrix (FR-GUI-065, subject fixed to STOP_HOLD by NORM-006).

import "./safety.css";

import { DummyModeBanner } from "./DummyModeBanner";
import { StatusBadgeBar, type RobotBadgeState } from "./StatusBadgeBar";
import { StopControls } from "./StopControls";
import type { CanInterfaceStatus } from "./canStatus";
import type { PushToHubState, VelocityTorqueState } from "./flags";
import type { SafetyContext } from "./modes";
import type { Notification } from "./notifications";

export interface GlobalSafetyBarProps {
  // The screen/mode/role the operator is currently in. Used for display only —
  // it never gates whether the stop pair renders.
  context: SafetyContext;
  robot: RobotBadgeState;
  canInterfaces: readonly CanInterfaceStatus[];
  velocityTorque: VelocityTorqueState;
  pushToHub: PushToHubState;
  notifications: readonly Notification[];
  dummyMode: boolean;
  onSoftStop: () => void;
  onToggleVelocityTorque: (enabled: boolean) => void;
}

export function GlobalSafetyBar({
  context,
  robot,
  canInterfaces,
  velocityTorque,
  pushToHub,
  notifications,
  dummyMode,
  onSoftStop,
  onToggleVelocityTorque,
}: GlobalSafetyBarProps) {
  const hasControl = context.role === "controller";
  return (
    <div className="oa-safety-bar" data-screen={context.screen} data-mode={context.mode}>
      <DummyModeBanner dummyMode={dummyMode} />
      <StatusBadgeBar
        robot={robot}
        canInterfaces={canInterfaces}
        velocityTorque={velocityTorque}
        pushToHub={pushToHub}
        notifications={notifications}
        onToggleVelocityTorque={onToggleVelocityTorque}
      />
      <StopControls onSoftStop={onSoftStop} hasControl={hasControl} />
    </div>
  );
}
