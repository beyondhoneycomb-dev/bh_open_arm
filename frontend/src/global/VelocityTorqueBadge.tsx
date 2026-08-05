// Always-on badge for use_velocity_and_torque (FR-GUI-072), exposed as the single
// coupled switch. When off it renders in a warning tone with the "torque/velocity
// not recorded" message. The onToggle prop carries a single boolean that the
// caller applies to both arms via setVelocityTorqueCoupled — there is no per-arm
// control here or anywhere in this WP (CG-G-03c).

import {
  FLAG_VALUE_UNKNOWN_LABEL,
  VELOCITY_TORQUE_OFF_WARNING,
  velocityTorqueIsUnknown,
  velocityTorqueIsWarning,
  type VelocityTorqueState,
} from "./flags";

export interface VelocityTorqueBadgeProps {
  state: VelocityTorqueState;
  // Coupled toggle: the single value applies to follower and leader together.
  onToggle: (enabled: boolean) => void;
}

// An unread flag takes the muted tone, not the nominal one. Nominal is this bar's
// "healthy" colour, and it may only appear for a value a session actually reported.
function toneFor(state: VelocityTorqueState): string {
  if (velocityTorqueIsUnknown(state)) {
    return "oa-badge--muted";
  }
  return velocityTorqueIsWarning(state) ? "oa-badge--warning" : "oa-badge--nominal";
}

function valueLabel(state: VelocityTorqueState): string {
  if (state.enabled === null) {
    return FLAG_VALUE_UNKNOWN_LABEL;
  }
  return state.enabled ? "ON" : "OFF";
}

export function VelocityTorqueBadge({ state, onToggle }: VelocityTorqueBadgeProps) {
  return (
    <span
      className={`oa-badge ${toneFor(state)}`}
      data-flag="use_velocity_and_torque"
      data-flag-value={state.enabled === null ? "unknown" : String(state.enabled)}
      role="status"
    >
      <span className="oa-badge__key">힘/컴플라이언스</span>
      <label className="oa-badge__switch">
        <input
          type="checkbox"
          checked={state.enabled === true}
          onChange={(event) => onToggle(event.target.checked)}
          aria-label="use_velocity_and_torque (팔로워·리더 커플드)"
        />
        <span className="oa-badge__value">{valueLabel(state)}</span>
      </label>
      {velocityTorqueIsWarning(state) && (
        <span className="oa-badge__warning">{VELOCITY_TORQUE_OFF_WARNING}</span>
      )}
    </span>
  );
}
