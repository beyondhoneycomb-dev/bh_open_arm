// The backend-Robot controls (FR-SIM-097 / row 205). Two things live here:
//   - the physics-backend selector (MuJoCo stage-1 canon vs Isaac stage-2), and
//   - the sim <-> real control-target toggle.
//
// The toggle swaps the backend `Robot` OBJECT only. It performs no reconnect, no
// disconnect and no connect: a browser-driven reconnect re-runs the backend
// Robot's set_zero_position and destroys zeroing (I-2), so the swap path is a pure
// state change plus an intent callback and nothing else. CG-G-S09c proves the path
// carries zero reconnect symbols by static scan.

import {
  CONTROL_TARGET_LABELS,
  SIM_BACKENDS,
  swapTarget,
  type ControlTarget,
  type SimBackend,
} from "./simDomain";

interface RobotBackendToggleProps {
  backend: SimBackend;
  controlTarget: ControlTarget;
  onSelectBackend: (backend: SimBackend) => void;
  onSwapTarget: (next: ControlTarget) => void;
}

const BACKEND_ORDER: readonly SimBackend[] = ["mujoco", "isaac"];

export function RobotBackendToggle({
  backend,
  controlTarget,
  onSelectBackend,
  onSwapTarget,
}: RobotBackendToggleProps) {
  const other = swapTarget(controlTarget);

  return (
    <section className="oa-sim__backend" aria-labelledby="oa-sim-backend-title">
      <h2 id="oa-sim-backend-title" className="oa-sim__section-title">
        백엔드 Robot
      </h2>

      <fieldset className="oa-sim__backend-picker">
        <legend>물리 백엔드 (FR-SIM-097)</legend>
        {BACKEND_ORDER.map((candidate) => (
          <label key={candidate}>
            <input
              type="radio"
              name="oa-sim-backend"
              value={candidate}
              checked={backend === candidate}
              onChange={() => onSelectBackend(candidate)}
            />
            {SIM_BACKENDS[candidate].label}
          </label>
        ))}
      </fieldset>

      <div className="oa-sim__target">
        <p className="oa-sim__target-current" role="status">
          제어 대상: <strong>{CONTROL_TARGET_LABELS[controlTarget]}</strong>
        </p>
        <button
          type="button"
          className="oa-sim__target-swap"
          onClick={() => onSwapTarget(other)}
        >
          대상 스왑 → {CONTROL_TARGET_LABELS[other]}
        </button>
        <p className="oa-sim__target-note" role="note">
          스왑은 백엔드 Robot 객체만 교체한다. 전송 채널·영점은 건드리지 않는다.
        </p>
      </div>
    </section>
  );
}
