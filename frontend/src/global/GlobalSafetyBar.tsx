// The always-on safety surface WP-G-03 delivers, mounted by the shell on every
// screen. It composes the dummy-mode banner, the status badge bar, and the two
// stop controls. Its defining property (CG-G-03b): the stop controls — the hard
// E-Stop in particular — are rendered unconditionally, independent of screen,
// mode, and whether this client holds control. The soft stop is gated on control
// authority (it is a control-authority action); the hard E-Stop is never gated,
// because cutting power must work for an observer too (FR-GUI-065).

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
  // it never gates the hard E-Stop.
  context: SafetyContext;
  robot: RobotBadgeState;
  canInterfaces: readonly CanInterfaceStatus[];
  velocityTorque: VelocityTorqueState;
  pushToHub: PushToHubState;
  notifications: readonly Notification[];
  dummyMode: boolean;
  onSoftStop: () => void;
  onHardEStop: () => void;
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
  onHardEStop,
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
      <StopControls
        onSoftStop={onSoftStop}
        onHardEStop={onHardEStop}
        hasControl={hasControl}
      />
    </div>
  );
}
