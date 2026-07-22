// Joint jog panel (WP-G-S04). Per-joint +/- jog for the active arm, with:
//  - hold-to-move in continuous mode: press emits a jog intent, release emits an
//    immediate STOP_HOLD (Cat 2), CG-G-S04f;
//  - a direction button disabled at the limit, only the opposite allowed, from the
//    backend's blockedDirection verdict — the screen never recomputes "at limit"
//    (CG-G-S04c / CG-G-S04a);
//  - rad AND deg positions plus every unit label (CG-G-S04e), and the active limit
//    set stated at all times (contract row: v2 URDF rad canon vs soft clamp).
//
// Every emission goes through onCommand, which the screen has already gated on
// arm+lease+freshness, so an unarmed press or a slider drag issues nothing
// (CG-G-S04b). The step size and speed scale are operator selections carried into
// the intent; the backend owns the actual velocity/step guard.

import type { ReactElement } from "react";

import type { ManualCommand, JogDirection, JogMode } from "./commands";
import type { ManualSource, JointReadout } from "./manualSource";

export interface JogPanelProps {
  source: ManualSource;
  mode: JogMode;
  onModeChange: (mode: JogMode) => void;
  stepSizeDeg: number;
  onStepSizeChange: (deg: number) => void;
  speedScalePct: number;
  onSpeedScaleChange: (pct: number) => void;
  canMove: boolean;
  onCommand: (command: ManualCommand) => void;
}

function jogCommand(
  props: JogPanelProps,
  joint: JointReadout,
  direction: JogDirection,
): ManualCommand {
  return {
    op: "jog_joint",
    side: props.source.side,
    jointIndex: joint.index,
    direction,
    mode: props.mode,
    stepSizeDeg: props.mode === "step" ? props.stepSizeDeg : null,
    speedScalePct: props.speedScalePct,
  };
}

function stopCommand(side: ManualSource["side"]): ManualCommand {
  return { op: "stop_hold", side };
}

function directionBlocked(joint: JointReadout, direction: JogDirection): boolean {
  return joint.blockedDirection === direction;
}

export function JogPanel(props: JogPanelProps) {
  const { source, mode, canMove, onCommand } = props;

  function pressDirection(joint: JointReadout, direction: JogDirection): void {
    if (mode === "continuous") {
      onCommand(jogCommand(props, joint, direction));
    }
  }

  function releaseDirection(): void {
    if (mode === "continuous") {
      onCommand(stopCommand(source.side));
    }
  }

  function clickDirection(joint: JointReadout, direction: JogDirection): void {
    if (mode === "step") {
      onCommand(jogCommand(props, joint, direction));
    }
  }

  function renderDirButton(joint: JointReadout, direction: JogDirection): ReactElement {
    const blocked = directionBlocked(joint, direction);
    const label = direction === "positive" ? "+" : "−";
    return (
      <button
        type="button"
        className="oa-man-jog__dir"
        data-joint={joint.index}
        data-direction={direction}
        disabled={!canMove || blocked}
        aria-label={`${joint.name} ${direction === "positive" ? "정방향" : "역방향"} 조그`}
        onPointerDown={() => pressDirection(joint, direction)}
        onPointerUp={() => releaseDirection()}
        onPointerLeave={() => releaseDirection()}
        onClick={() => clickDirection(joint, direction)}
      >
        {label}
      </button>
    );
  }

  return (
    <section className="oa-man-jog" aria-labelledby="oa-man-jog-title">
      <header className="oa-man-jog__head">
        <h2 id="oa-man-jog-title">관절 조그 — {source.side} 팔</h2>
        <p className="oa-man-jog__limitset" data-field="active-limit-set">
          활성 리밋 세트: {source.limitSet.label}
        </p>
      </header>

      <div className="oa-man-jog__controls" role="group" aria-label="조그 모드">
        <fieldset className="oa-man-jog__mode">
          <legend>모드</legend>
          <label>
            <input
              type="radio"
              name="oa-man-jog-mode"
              checked={mode === "continuous"}
              onChange={() => props.onModeChange("continuous")}
            />
            연속 (hold-to-move)
          </label>
          <label>
            <input
              type="radio"
              name="oa-man-jog-mode"
              checked={mode === "step"}
              onChange={() => props.onModeChange("step")}
            />
            스텝
          </label>
        </fieldset>

        <label className="oa-man-jog__step">
          스텝 크기 (deg)
          <select
            value={props.stepSizeDeg}
            disabled={mode !== "step"}
            onChange={(event) => props.onStepSizeChange(Number(event.target.value))}
          >
            {source.jogStepSizesDeg.map((deg) => (
              <option key={deg} value={deg}>
                {deg}
              </option>
            ))}
          </select>
        </label>

        <label className="oa-man-jog__speed">
          속도 스케일: {props.speedScalePct}%
          <input
            type="range"
            min={0}
            max={100}
            value={props.speedScalePct}
            aria-label="속도 스케일 퍼센트"
            onChange={(event) => props.onSpeedScaleChange(Number(event.target.value))}
          />
        </label>
      </div>

      <table className="oa-man-jog__table">
        <thead>
          <tr>
            <th>관절</th>
            <th>위치 (rad)</th>
            <th>위치 (deg)</th>
            <th>속도 (rad·s⁻¹)</th>
            <th>토크 (Nm)</th>
            <th>온도 T_MOS/T_Rotor (°C)</th>
            <th>리밋 (rad)</th>
            <th>조그</th>
          </tr>
        </thead>
        <tbody>
          {source.joints.map((joint) => (
            <tr key={joint.index} data-joint-row={joint.index}>
              <td>{joint.name}</td>
              <td data-unit="rad">{joint.positionRad.toFixed(4)}</td>
              <td data-unit="deg">{joint.positionDeg.toFixed(1)}</td>
              <td data-unit="rad/s">{joint.velocityRadPerSec.toFixed(3)}</td>
              <td data-unit="Nm">{joint.torqueNm.toFixed(2)}</td>
              <td data-unit="degC">
                {joint.tempMosC.toFixed(0)}/{joint.tempRotorC.toFixed(0)}
              </td>
              <td data-unit="rad">
                [{joint.limitLoRad.toFixed(4)}, {joint.limitHiRad.toFixed(4)}]
                {joint.nearLimit && (
                  <span className="oa-man-jog__near" role="note" data-near-limit={joint.index}>
                    리밋 근접
                  </span>
                )}
              </td>
              <td className="oa-man-jog__dirs">
                {renderDirButton(joint, "negative")}
                {renderDirButton(joint, "positive")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
