// CG-G-02c (unit level): the ROS Z-up asset renders upright in the Y-up scene. The
// golden-screenshot regression is browser-only; here we prove the transform maths
// stands the robot up — ROS +Z (up) maps to Three +Y (up), not into the screen.

import { Object3D, Vector3 } from "three";
import { describe, expect, it } from "vitest";

import { applyWorldFrame, rosToThreeQuaternion, transformRosPoint } from "./coordinateTransform";

describe("CG-G-02c ROS Z-up -> Three Y-up transform", () => {
  it("sends ROS up (+Z) to Three up (+Y)", () => {
    const up = transformRosPoint(new Vector3(0, 0, 1));
    expect(up.x).toBeCloseTo(0);
    expect(up.y).toBeCloseTo(1);
    expect(up.z).toBeCloseTo(0);
  });

  it("keeps ROS forward (+X) as Three forward (+X)", () => {
    const forward = transformRosPoint(new Vector3(1, 0, 0));
    expect(forward.x).toBeCloseTo(1);
    expect(forward.y).toBeCloseTo(0);
    expect(forward.z).toBeCloseTo(0);
  });

  it("is not the identity — ROS up does not stay along Three +Z (robot not lying down)", () => {
    const up = transformRosPoint(new Vector3(0, 0, 1));
    expect(up.z).not.toBeCloseTo(1);
  });

  it("applies the world frame to a scene-root object", () => {
    const root = new Object3D();
    applyWorldFrame(root);
    expect(root.quaternion.equals(rosToThreeQuaternion())).toBe(true);
  });
});
