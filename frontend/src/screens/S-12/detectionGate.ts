// The gate that decides whether the screen may expose any path to enable
// collision detection. Two backend preconditions force detection OFF, and both
// are SAF domain facts the screen only renders:
//
//   - PG-FRIC-001 (friction model identification). Until v2.0 friction is
//     identified, residuals from an unidentified model false-trigger and
//     false-miss, so FR-SAF-030 forces detection DISABLED and requires a
//     standing banner. This is the gate CG-G-S12b turns on.
//   - use_velocity_and_torque (FR-SAF-072). With torque observation off there is
//     no tau_meas, so the GMO residual cannot be computed and enabling detection
//     is refused.
//
// When either precondition is unmet, enableAllowed is false and the screen
// renders NO enable control at all — the enable path is absent, not merely
// disabled — plus a standing banner. The screen never overrides this: the
// backend holds detection at DISABLED and this module reports that state.

export type FrictionGateOutcome = "passed" | "not_passed";

export type DetectionBlocker = "friction_unidentified" | "torque_observation_off";

export interface DetectionGateInput {
  // PG-FRIC-001 outcome as reported by the backend.
  frictionGate: FrictionGateOutcome;
  // use_velocity_and_torque coupled flag (FR-SAF-072); torque observation
  // presence, without which residual detection cannot run.
  torqueObservationEnabled: boolean;
}

export interface DetectionGateState {
  // Whether the screen may expose any enable-detection control.
  enableAllowed: boolean;
  // The status the backend forces detection to while the gate is unmet.
  forcedStatus: "DISABLED" | null;
  // Standing banner text, or null when detection is permitted.
  bannerText: string | null;
  // Every unmet precondition, friction first (it is the FAIL-blocking one).
  blockers: DetectionBlocker[];
}

// FR-SAF-030: the standing banner shown while the v2 friction model is not
// identified. Detection is disabled and stays disabled until PG-FRIC-001 passes.
export const FRICTION_UNIDENTIFIED_BANNER =
  "v2.0 마찰 모델 미식별 (PG-FRIC-001 미통과) — 충돌 감지 비활성 강제 (FR-SAF-030)";

// FR-SAF-072: shown when torque observation is off, which removes the residual's
// input entirely and makes enabling detection a refused request.
export const TORQUE_OBSERVATION_OFF_BANNER =
  "use_velocity_and_torque OFF — τ_meas 없음, 충돌 감지 활성화 거부 (FR-SAF-072)";

const BLOCKER_BANNERS: Readonly<Record<DetectionBlocker, string>> = {
  friction_unidentified: FRICTION_UNIDENTIFIED_BANNER,
  torque_observation_off: TORQUE_OBSERVATION_OFF_BANNER,
};

export function evaluateDetectionGate(input: DetectionGateInput): DetectionGateState {
  const blockers: DetectionBlocker[] = [];
  if (input.frictionGate !== "passed") {
    blockers.push("friction_unidentified");
  }
  if (!input.torqueObservationEnabled) {
    blockers.push("torque_observation_off");
  }

  const enableAllowed = blockers.length === 0;
  return {
    enableAllowed,
    forcedStatus: enableAllowed ? null : "DISABLED",
    bannerText: enableAllowed ? null : BLOCKER_BANNERS[blockers[0]],
    blockers,
  };
}
