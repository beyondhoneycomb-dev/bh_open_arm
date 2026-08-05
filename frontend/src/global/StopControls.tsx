// The always-visible safety pair (CG-G-03a). Two elements that can never be mistaken
// for each other, because only one of them is a control: the soft stop is a button
// that sends STOP_HOLD, and the hard E-Stop is a panel naming the physical button on
// the power line. There is no hard-stop handler prop to wire, which is what keeps a
// later caller from re-creating a button that reaches nothing (NORM-007). The standing
// drop warning (role="alert") stays beside the hard panel regardless of scroll or modal
// state — removing the button does not remove the hazard it described (FR-GUI-064).
//
// The soft stop is pressable by every client, never disabled. FR-GUI-065 requires it
// reachable independently of who holds control, and CTR-WS@v2 carries STOP_HOLD as a
// `stop_hold` frame with `control_frame: false`, so the server does not refuse it from
// a client holding no lease. Whoever sees the arm moving wrongly is who needs to stop
// it, and that is not always the lease holder.

import { HARD_ESTOP_DROP_WARNING, PHYSICAL_ESTOP, SOFT_STOP } from "./stopControls";

export interface StopControlsProps {
  // Soft stop: sends STOP_HOLD. Wired for every client — control authority is not a
  // precondition for stopping (FR-GUI-065, `stop_hold` is not a control frame).
  onSoftStop: () => void;
}

export function StopControls({ onSoftStop }: StopControlsProps) {
  return (
    <div className="oa-stops" role="group" aria-label="정지 컨트롤">
      <button
        type="button"
        className="oa-stop oa-stop--soft"
        data-stop-kind={SOFT_STOP.kind}
        onClick={onSoftStop}
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
