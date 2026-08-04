// The always-visible safety pair (CG-G-03a). Two elements that can never be mistaken
// for each other, because only one of them is a control: the soft stop is a button
// that sends STOP_HOLD, and the hard E-Stop is a panel naming the physical button on
// the power line. There is no hard-stop handler prop to wire, which is what keeps a
// later caller from re-creating a button that reaches nothing (NORM-007). The standing
// drop warning (role="alert") stays beside the hard panel regardless of scroll or modal
// state — removing the button does not remove the hazard it described (FR-GUI-064).

import { HARD_ESTOP_DROP_WARNING, PHYSICAL_ESTOP, SOFT_STOP } from "./stopControls";

export interface StopControlsProps {
  // Soft stop: sends STOP_HOLD. May be gated when this client is not the control
  // holder, since a soft stop is a control-authority action.
  onSoftStop: () => void;
  // Whether this client holds control. Only the soft stop honours it.
  hasControl: boolean;
}

export function StopControls({ onSoftStop, hasControl }: StopControlsProps) {
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
        <div className="oa-stop oa-stop--hard" data-stop-kind={PHYSICAL_ESTOP.kind}>
          <span className="oa-stop__label">{PHYSICAL_ESTOP.label}</span>
          <span className="oa-stop__effect">{PHYSICAL_ESTOP.effect}</span>
          <span className="oa-stop__actuation">{PHYSICAL_ESTOP.actuation}</span>
        </div>
        <p className="oa-stop__drop-warning" role="alert">
          {HARD_ESTOP_DROP_WARNING}
        </p>
      </div>
    </div>
  );
}
