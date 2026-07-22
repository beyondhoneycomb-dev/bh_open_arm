// The two always-visible safety stops (CG-G-03a). Rendered as two visually and
// structurally distinct controls: a soft stop (torque hold) and a hard E-Stop
// (power cut -> drop), each calling its own handler prop so the two outcomes can
// never share a code path. The hard E-Stop carries a standing drop warning
// (role="alert") rendered unconditionally beside it, so it stays visible
// regardless of scroll or modal state. The E-Stop is never disabled: a client
// that cannot command control (observer) can still cut power.

import {
  HARD_ESTOP,
  HARD_ESTOP_DROP_WARNING,
  SOFT_STOP,
} from "./stopControls";

export interface StopControlsProps {
  // Soft stop: sends STOP_HOLD. May be gated when this client is not the control
  // holder, since a soft stop is a control-authority action.
  onSoftStop: () => void;
  // Hard E-Stop: cuts power. Never gated (FR-GUI-065) — always callable.
  onHardEStop: () => void;
  // Whether this client holds control. Only the soft stop honours it; the hard
  // E-Stop ignores it by design.
  hasControl: boolean;
}

export function StopControls({ onSoftStop, onHardEStop, hasControl }: StopControlsProps) {
  return (
    <div className="oa-stops" role="group" aria-label="정지 컨트롤">
      <button
        type="button"
        className="oa-stop oa-stop--soft"
        data-stop-kind={SOFT_STOP.kind}
        onClick={onSoftStop}
        disabled={!hasControl}
        title={SOFT_STOP.effect}
      >
        <span className="oa-stop__label">{SOFT_STOP.label}</span>
        <span className="oa-stop__effect">{SOFT_STOP.effect}</span>
      </button>

      <div className="oa-stop-hard">
        <button
          type="button"
          className="oa-stop oa-stop--hard"
          data-stop-kind={HARD_ESTOP.kind}
          onClick={onHardEStop}
          title={HARD_ESTOP.effect}
        >
          <span className="oa-stop__label">{HARD_ESTOP.label}</span>
          <span className="oa-stop__effect">{HARD_ESTOP.effect}</span>
        </button>
        <p className="oa-stop__drop-warning" role="alert">
          {HARD_ESTOP_DROP_WARNING}
        </p>
      </div>
    </div>
  );
}
