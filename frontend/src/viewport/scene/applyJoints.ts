// Apply an accepted joint snapshot to a loaded URDF robot. The values are in
// RADIANS, keyed by URDF joint name, exactly as the backend produced them — the
// batch setter takes radians and the browser passes them straight through. The
// browser performs no deg/rad conversion (CTR-UNIT@v1, backend-owned) and calls
// no degree-valued single-joint setter (CG-G-02a); only this batch, radian path
// exists. Decoupled from urdf-loader behind a minimal interface so it is testable
// without a real robot or a WebGL context.

// The single capability the viewport needs from a loaded URDF robot: set every
// joint at once from a name->radians map. URDFRobot from urdf-loader satisfies it.
export interface JointTarget {
  setJointValues(values: { [jointName: string]: number }): boolean;
}

// Push an accepted full-joint snapshot onto the robot. `positionsRad` has already
// been validated as a full snapshot (acceptSnapshot); this only forwards it.
export function applyJointSnapshot(
  target: JointTarget,
  positionsRad: Readonly<Record<string, number>>,
): boolean {
  return target.setJointValues({ ...positionsRad });
}
