// End-effector FK reconciliation (CG-G-02f). The EE numeric canon is the backend
// openarm_control MJCF FK, because the thing that makes the command is the MJCF.
// The browser may compute an auxiliary FK for display, but it never substitutes
// its own number: reconciliation always returns the backend pose. When a browser
// aux pose is supplied and disagrees beyond tolerance, that only raises a warning
// so the disagreement is visible — the value shown is still the backend's.

import { EE_FK_TOLERANCE_M } from "../constants";

export interface EePose {
  // Metres, in the backend's task frame. The viewport does not transform these
  // (the Z-up->Y-up transform is applied to the rendered scene, not to canon FK).
  readonly x: number;
  readonly y: number;
  readonly z: number;
}

export interface FkReconcileResult {
  // Always the backend pose — the browser never wins an EE disagreement.
  readonly pose: EePose;
  // True when a browser aux pose was supplied and diverged beyond tolerance.
  readonly warned: boolean;
  // The measured divergence in metres (0 when no aux pose was supplied).
  readonly deltaM: number;
}

function distance(a: EePose, b: EePose): number {
  const dx = a.x - b.x;
  const dy = a.y - b.y;
  const dz = a.z - b.z;
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

export function reconcileEndEffector(
  backendPose: EePose,
  browserAuxPose: EePose | null,
  toleranceM: number = EE_FK_TOLERANCE_M,
): FkReconcileResult {
  if (browserAuxPose === null) {
    return { pose: backendPose, warned: false, deltaM: 0 };
  }
  const deltaM = distance(backendPose, browserAuxPose);
  return { pose: backendPose, warned: deltaM > toleranceM, deltaM };
}
