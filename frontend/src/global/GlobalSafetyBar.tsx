// The always-on safety surface WP-G-03 delivers. The shell mounts it in Layout above
// the route outlet, so it is on screen for every route. It composes the dummy-mode
// banner, the status badge bar, and the stop pair. Its defining property (CG-G-03b):
// the pair is rendered unconditionally and the STOP_HOLD control is pressable in all
// 208 cells of the matrix, alongside the physical-E-Stop guidance — screen, mode and
// control authority change nothing about either (FR-GUI-065, subject fixed to
// STOP_HOLD by NORM-006).
//
// Every prop is the caller's observation, and each admits an explicit unknown. The bar
// renders what it was told and asserts nothing on its own: with no session the badges
// read disconnected/unknown rather than nominal, because a safety surface claiming a
// healthy robot it never observed is worse than one that admits it knows nothing.

import "./safety.css";

import { DummyModeBanner } from "./DummyModeBanner";
import { StatusBadgeBar, type RobotBadgeState } from "./StatusBadgeBar";
import { StopControls } from "./StopControls";
import type { CanInterfaceStatus } from "./canStatus";
import type { PushToHubState, VelocityTorqueState } from "./flags";
import type { SafetyContext } from "./modes";
import type { Notification } from "./notifications";

export interface GlobalSafetyBarProps {
  // The screen/mode/role the operator is currently in. Used for display only — it
  // gates neither whether the stop pair renders nor whether it is pressable.
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
      <StopControls onSoftStop={onSoftStop} />
    </div>
  );
}
