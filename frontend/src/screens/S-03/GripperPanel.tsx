// The gripper (J8) POS_FORCE + endpoint-capture panel. Two hard rules live here:
//
//  1. The POS_FORCE second value is torque_pu, a per-unit current limit in [0,1]
//     (03 §2.10) — it is NOT a torque in newton-metres and NOT a grasp force in
//     newtons. pu↔N is unmeasured, so this panel labels the value torque_pu and
//     shows no force-unit label at all (CG-G-S03a). This file deliberately
//     contains no force-unit token.
//
//  2. The gripper motor's configured POS_FORCE speed can exceed its physical vMax
//     (03 §2.10 note). The panel shows the REACHABLE speed = min(configured,
//     vMax) via effectiveGripperSpeedRadS, with vMax taken from the injected
//     descriptor — never a literal — so the misleading raw figure is never shown
//     as if it were achievable (CG-G-S03f).
//
// Endpoint capture (WP-2A-08): the operator places the gripper at each physical
// end and the backend records the native rad; norm∈[0,1] is the backend's linear
// interpolation. The panel renders capture state and emits the capture intent; it
// computes no opening in mm and no motor:finger ratio (both unmeasured, 03 §2.10).

import {
  TORQUE_PU_LABEL,
  effectiveGripperSpeedRadS,
  gripperSpeedExceedsVMax,
  type GripperState,
} from "./motorDomain";

interface GripperPanelProps {
  gripper: GripperState | null;
  onCaptureEndpoint: (which: "open" | "close") => void;
}

function rad(value: number | null): string {
  return value === null ? "미캡처 (uncaptured)" : `${value} rad`;
}

export function GripperPanel({ gripper, onCaptureEndpoint }: GripperPanelProps) {
  if (!gripper) {
    return (
      <section className="oa-motors__panel" aria-labelledby="oa-motors-gripper-title">
        <h2 id="oa-motors-gripper-title" className="oa-motors__panel-title">
          그리퍼 (J8) · POS_FORCE
        </h2>
        <p className="oa-motors__hint" role="status">
          그리퍼 상태 미가용 (awaiting backend)
        </p>
      </section>
    );
  }

  const reachableSpeed = effectiveGripperSpeedRadS(
    gripper.configuredSpeedRadS,
    gripper.motorVMaxRadS,
  );
  const capped = gripperSpeedExceedsVMax(gripper.configuredSpeedRadS, gripper.motorVMaxRadS);

  return (
    <section className="oa-motors__panel" aria-labelledby="oa-motors-gripper-title">
      <h2 id="oa-motors-gripper-title" className="oa-motors__panel-title">
        그리퍼 (J8) · POS_FORCE
      </h2>

      <div className="oa-motors__gripper-force">
        <span>
          <strong>{TORQUE_PU_LABEL}</strong>: <span data-gripper-torque-pu>{gripper.torquePu}</span>
        </span>
        <span className="oa-motors__hint">
          per-unit = 실제 전류 / 최대 전류. 물리 파지력 단위는 미확정이므로 표시하지 않는다.
        </span>
      </div>

      <p>
        <span>속도 (실현가능): </span>
        <span data-gripper-speed-reachable>{reachableSpeed}</span>
        <span> rad/s</span>
      </p>
      {capped && (
        <p className="oa-motors__speed-note" data-gripper-speed-capped role="status">
          설정 속도 {gripper.configuredSpeedRadS} rad/s 는 이 모터의 vMax{" "}
          {gripper.motorVMaxRadS} rad/s 를 초과 — 도달 불가, 실현가능 값으로 표시.
        </p>
      )}

      <div>
        <p>
          <span>Open 엔드포인트: </span>
          <span data-gripper-open-rad>{rad(gripper.openRad)}</span>
        </p>
        <p>
          <span>Close 엔드포인트: </span>
          <span data-gripper-close-rad>{rad(gripper.closeRad)}</span>
        </p>
        <button
          type="button"
          className="oa-motors__button"
          data-action="capture-open"
          onClick={() => onCaptureEndpoint("open")}
        >
          현재 자세를 Open 으로 캡처
        </button>
        <button
          type="button"
          className="oa-motors__button"
          data-action="capture-close"
          onClick={() => onCaptureEndpoint("close")}
        >
          현재 자세를 Close 로 캡처
        </button>
      </div>
    </section>
  );
}
