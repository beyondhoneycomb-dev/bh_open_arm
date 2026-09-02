// Building a model frame from a rig frame.
//
// The two do not have the same joint set: the bus reports every joint including both grippers,
// and the model declares the ones it has. What must survive that difference is the acceptance
// gate — a joint the model declares and the frame does not carry is still a refused snapshot,
// because `get_observation()` fills a missing motor with zero and a partial frame overlaid on
// the last one draws a dead motor at a plausible angle.

import { describe, expect, it } from "vitest";

import { acceptSnapshot, jointFrameFor } from "./jointSnapshot";

const MODEL_JOINTS = ["openarm_left_joint1", "openarm_left_joint2"];
const FRAME_AT_MS = 1234;

const REPORTED = [
  { name: "openarm_left_joint1", positionRad: 0.25 },
  { name: "openarm_left_joint2", positionRad: -0.5 },
  // On the bus, absent from the model's declared set.
  { name: "openarm_left_finger_joint1", positionRad: 0.02 },
];

describe("jointFrameFor", () => {
  it("carries the model's joints and the backend's radians, untouched", () => {
    const frame = jointFrameFor(REPORTED, MODEL_JOINTS, FRAME_AT_MS);

    expect(frame.positionsRad).toEqual({
      openarm_left_joint1: 0.25,
      openarm_left_joint2: -0.5,
    });
    expect(frame.frameMonoMs).toBe(FRAME_AT_MS);
  });

  it("leaves out a joint the model does not declare", () => {
    // The gripper is real and on the wire. Passing it through would make every frame fail
    // acceptance as "unexpected-joint" against a model that simply does not have it.
    const frame = jointFrameFor(REPORTED, MODEL_JOINTS, FRAME_AT_MS);

    expect(Object.keys(frame.positionsRad)).not.toContain("openarm_left_finger_joint1");
    expect(acceptSnapshot(frame, MODEL_JOINTS).accepted).toBe(true);
  });

  it("still produces a refused snapshot when the frame is missing a declared joint", () => {
    // The failure the gate exists for, and the one filtering must not hide.
    const frame = jointFrameFor(REPORTED.slice(0, 1), MODEL_JOINTS, FRAME_AT_MS);
    const result = acceptSnapshot(frame, MODEL_JOINTS);

    expect(result.accepted).toBe(false);
    if (!result.accepted) {
      expect(result.reason).toBe("partial-joint-frame");
      expect(result.missing).toEqual(["openarm_left_joint2"]);
    }
  });

  it("produces an empty frame when nothing was reported, not a frame of zeros", () => {
    const frame = jointFrameFor([], MODEL_JOINTS, FRAME_AT_MS);

    expect(frame.positionsRad).toEqual({});
    expect(acceptSnapshot(frame, MODEL_JOINTS).accepted).toBe(false);
  });
});
