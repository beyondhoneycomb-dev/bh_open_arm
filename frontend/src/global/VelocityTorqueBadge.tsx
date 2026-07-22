// Always-on badge for use_velocity_and_torque (FR-GUI-072), exposed as the single
// coupled switch. When off it renders in a warning tone with the "torque/velocity
// not recorded" message. The onToggle prop carries a single boolean that the
// caller applies to both arms via setVelocityTorqueCoupled — there is no per-arm
// control here or anywhere in this WP (CG-G-03c).

import {
  VELOCITY_TORQUE_OFF_WARNING,
  velocityTorqueIsWarning,
  type VelocityTorqueState,
} from "./flags";

export interface VelocityTorqueBadgeProps {
  state: VelocityTorqueState;
  // Coupled toggle: the single value applies to follower and leader together.
  onToggle: (enabled: boolean) => void;
}

export function VelocityTorqueBadge({ state, onToggle }: VelocityTorqueBadgeProps) {
  const warning = velocityTorqueIsWarning(state);
  return (
    <span
      className={`oa-badge ${warning ? "oa-badge--warning" : "oa-badge--nominal"}`}
      data-flag="use_velocity_and_torque"
      role="status"
    >
      <span className="oa-badge__key">힘/컴플라이언스</span>
      <label className="oa-badge__switch">
        <input
          type="checkbox"
          checked={state.enabled}
          onChange={(event) => onToggle(event.target.checked)}
          aria-label="use_velocity_and_torque (팔로워·리더 커플드)"
        />
        <span className="oa-badge__value">{state.enabled ? "ON" : "OFF"}</span>
      </label>
      {warning && <span className="oa-badge__warning">{VELOCITY_TORQUE_OFF_WARNING}</span>}
    </span>
  );
}
