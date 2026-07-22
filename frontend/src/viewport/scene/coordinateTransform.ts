// The one coordinate transform the browser owns: ROS Z-up -> Three.js Y-up
// (CG-G-02c). ROS describes the robot with Z pointing up; Three.js renders with Y
// up. A -90 degree rotation about X carries ROS +Z onto Three +Y, so the robot
// stands upright. Getting this wrong throws no error — the robot merely lies on
// its side, and an EE drag attached to a sideways robot inverts the operator's
// motion. This is a rendering rotation applied to the scene root, NOT a physical
// unit conversion (those are CTR-UNIT@v1, backend-owned, and never done here).

import { Euler, Object3D, Quaternion, Vector3 } from "three";

import { ROS_TO_THREE_ROTATION_X } from "../constants";

// The world-frame rotation as a quaternion. Freshly constructed each call so no
// caller can mutate a shared instance.
export function rosToThreeQuaternion(): Quaternion {
  return new Quaternion().setFromEuler(new Euler(ROS_TO_THREE_ROTATION_X, 0, 0));
}

// Map a point expressed in the ROS frame into the Three.js render frame. Used for
// tests and for placing render-only decorations; canonical FK numbers are never
// routed through here.
export function transformRosPoint(rosPoint: Vector3): Vector3 {
  return rosPoint.clone().applyQuaternion(rosToThreeQuaternion());
}

// Orient a scene-root object so its ROS-authored children render Y-up. Applied to
// the URDF robot root once, at mount.
export function applyWorldFrame(root: Object3D): void {
  root.quaternion.copy(rosToThreeQuaternion());
}
