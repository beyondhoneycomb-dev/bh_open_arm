// Cartesian jog panel (WP-G-S04). Six translation and six rotation directions, a
// reference-frame selector (base/tool/world), and every axis carrying its unit
// and frame label (CG-G-S04e). base and world share a rotation and differ only in
// origin, which the panel states so the operator does not expect different axes
// (FR-MAN-019).
//
// The IK backend (openarm_control) is the domain's (FR-MAN-020); the panel renders
// its tuning read-only and surfaces an IK failure instead of letting a step be
// silently skipped (FR-MAN-025). The panel neither runs IK nor clamps a solution.
// Emission is gated the same way as joint jog (CG-G-S04b/f): press jogs, release
// holds, and an unarmed press sends nothing.

import type { ReactElement } from "react";

import type {
  ManualCommand,
  JogDirection,
  JogMode,
  CartesianAxis,
  ReferenceFrame,
} from "./commands";
import type { ManualSource } from "./manualSource";

export interface CartesianPanelProps {
  source: ManualSource;
  mode: JogMode;
  onModeChange: (mode: JogMode) => void;
  activeFrame: ReferenceFrame;
  onFrameChange: (frame: ReferenceFrame) => void;
  translationStepMm: number;
  onTranslationStepChange: (mm: number) => void;
  rotationStepDeg: number;
  onRotationStepChange: (deg: number) => void;
  speedScalePct: number;
  canMove: boolean;
  onCommand: (command: ManualCommand) => void;
}

interface AxisSpec {
  axis: CartesianAxis;
  label: string;
  unit: "mm" | "deg";
}

const TRANSLATION_AXES: readonly AxisSpec[] = [
  { axis: "x", label: "X", unit: "mm" },
  { axis: "y", label: "Y", unit: "mm" },
  { axis: "z", label: "Z", unit: "mm" },
];

const ROTATION_AXES: readonly AxisSpec[] = [
  { axis: "roll", label: "R", unit: "deg" },
  { axis: "pitch", label: "P", unit: "deg" },
  { axis: "yaw", label: "Y", unit: "deg" },
];

export function CartesianPanel(props: CartesianPanelProps) {
  const { source, mode, activeFrame, canMove, onCommand } = props;

  function cartesianCommand(spec: AxisSpec, direction: JogDirection): ManualCommand {
    return {
      op: "jog_cartesian",
      side: source.side,
      axis: spec.axis,
      direction,
      frame: activeFrame,
      mode,
      stepSize:
        mode === "step"
          ? spec.unit === "mm"
            ? props.translationStepMm
            : props.rotationStepDeg
          : null,
      speedScalePct: props.speedScalePct,
    };
  }

  function pressAxis(spec: AxisSpec, direction: JogDirection): void {
    if (mode === "continuous") {
      onCommand(cartesianCommand(spec, direction));
    }
  }

  function releaseAxis(): void {
    if (mode === "continuous") {
      onCommand({ op: "stop_hold", side: source.side });
    }
  }

  function clickAxis(spec: AxisSpec, direction: JogDirection): void {
    if (mode === "step") {
      onCommand(cartesianCommand(spec, direction));
    }
  }

  function renderAxis(spec: AxisSpec): ReactElement {
    return (
      <div key={spec.axis} className="oa-man-cart__axis" data-axis={spec.axis}>
        <span className="oa-man-cart__axis-label">
          {spec.label} <span data-unit={spec.unit}>({spec.unit})</span>
        </span>
        {(["negative", "positive"] as const).map((direction) => (
          <button
            key={direction}
            type="button"
            className="oa-man-cart__dir"
            data-axis={spec.axis}
            data-direction={direction}
            disabled={!canMove}
            aria-label={`${spec.label} ${direction === "positive" ? "정방향" : "역방향"} (${activeFrame} 프레임)`}
            onPointerDown={() => pressAxis(spec, direction)}
            onPointerUp={() => releaseAxis()}
            onPointerLeave={() => releaseAxis()}
            onClick={() => clickAxis(spec, direction)}
          >
            {direction === "positive" ? "+" : "−"}
          </button>
        ))}
      </div>
    );
  }

  const ik = source.ik;
  return (
    <section className="oa-man-cart" aria-labelledby="oa-man-cart-title">
      <header className="oa-man-cart__head">
        <h2 id="oa-man-cart-title">카테시안 조그 — {source.side} 팔</h2>
        <p className="oa-man-cart__cp" data-field="control-point">
          제어점: {source.ee.controlPointLabel}
          {!source.ee.tcpIsGraspPoint && <span> (기본값은 파지점 아님 — 손목)</span>}
        </p>
      </header>

      <fieldset className="oa-man-cart__frame" data-field="reference-frame">
        <legend>기준 프레임</legend>
        {source.cartesian.frames.map((frame) => (
          <label key={frame}>
            <input
              type="radio"
              name="oa-man-cart-frame"
              checked={activeFrame === frame}
              onChange={() => props.onFrameChange(frame)}
            />
            {frame}
          </label>
        ))}
        <p className="oa-man-cart__frame-note" role="note">
          {source.cartesian.baseWorldNote}
        </p>
      </fieldset>

      <div className="oa-man-cart__controls" role="group" aria-label="카테시안 조그 모드">
        <fieldset className="oa-man-cart__mode">
          <legend>모드</legend>
          <label>
            <input
              type="radio"
              name="oa-man-cart-mode"
              checked={mode === "continuous"}
              onChange={() => props.onModeChange("continuous")}
            />
            연속
          </label>
          <label>
            <input
              type="radio"
              name="oa-man-cart-mode"
              checked={mode === "step"}
              onChange={() => props.onModeChange("step")}
            />
            스텝
          </label>
        </fieldset>
        <label>
          병진 스텝 (mm)
          <select
            value={props.translationStepMm}
            disabled={mode !== "step"}
            onChange={(event) => props.onTranslationStepChange(Number(event.target.value))}
          >
            {source.cartesian.translationStepsMm.map((mm) => (
              <option key={mm} value={mm}>
                {mm}
              </option>
            ))}
          </select>
        </label>
        <label>
          회전 스텝 (deg)
          <select
            value={props.rotationStepDeg}
            disabled={mode !== "step"}
            onChange={(event) => props.onRotationStepChange(Number(event.target.value))}
          >
            {source.cartesian.rotationStepsDeg.map((deg) => (
              <option key={deg} value={deg}>
                {deg}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="oa-man-cart__grid">
        <div className="oa-man-cart__group" aria-label="병진">
          <h3>병진</h3>
          {TRANSLATION_AXES.map(renderAxis)}
        </div>
        <div className="oa-man-cart__group" aria-label="회전">
          <h3>회전</h3>
          {ROTATION_AXES.map(renderAxis)}
        </div>
      </div>

      <dl className="oa-man-cart__ee" aria-label="EE 포즈">
        <div>
          <dt>X/Y/Z</dt>
          <dd data-unit="mm">
            {source.ee.xMm.toFixed(1)} / {source.ee.yMm.toFixed(1)} / {source.ee.zMm.toFixed(1)} mm
            (world)
          </dd>
        </div>
        <div>
          <dt>R/P/Y</dt>
          <dd data-unit="deg">
            {source.ee.rollDeg.toFixed(1)} / {source.ee.pitchDeg.toFixed(1)} /{" "}
            {source.ee.yawDeg.toFixed(1)} deg (world)
          </dd>
        </div>
      </dl>

      <details className="oa-man-cart__ik" data-field="ik-status">
        <summary>IK 파라미터 (openarm_control)</summary>
        <p className="oa-man-cart__ik-note" role="note">
          {ik.libraryDefaultNote}
        </p>
        <ul>
          <li>damping (Tikhonov): {ik.dampingTikhonov}</li>
          <li>lm_damping: {ik.lmDamping}</li>
          <li>posture_cost: {ik.postureCost}</li>
          <li>
            position/orientation_cost: {ik.positionCost}/{ik.orientationCost}
          </li>
          <li>dt: {ik.dt}</li>
          <li>max_iters: {ik.maxIters}</li>
          <li>solver: {ik.solver}</li>
        </ul>
        {ik.singularityNear && (
          <p className="oa-man-cart__ik-warn" role="alert">
            특이점 근접 — 속도 감쇠
          </p>
        )}
        {ik.lastFailure && (
          <p className="oa-man-cart__ik-fail" role="alert" data-ik-failure={ik.lastFailure.reason}>
            IK 실패: {ik.lastFailure.message}
          </p>
        )}
      </details>
    </section>
  );
}
