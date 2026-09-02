// Per-frame full-joint snapshot (CG-G-02d). The viewport renders exactly the
// joints the backend reports, in radians, keyed by URDF joint name. It does not
// convert units — CTR-UNIT@v1 (backend) owns the deg/rad boundary and the joint
// namespace map — and it does not merge a frame into a retained prior state.
//
// A frame that does not carry EVERY expected joint is REJECTED, never merged:
// get_observation() fills a missing motor with 0, so a view that overlaid a
// partial frame onto the last one would draw a dead motor at a plausible angle
// and call it live. The gate refuses the partial frame outright; the last fully
// accepted snapshot keeps showing, and its age is what stream-age then flags.

export interface JointFrame {
  // URDF joint name -> angle in RADIANS, exactly as the backend produced it. No
  // conversion, no renaming: the browser is a window onto the backend's numbers.
  readonly positionsRad: Readonly<Record<string, number>>;
  // Monotonic timestamp (ms) the frame was produced, for age/stale evaluation.
  readonly frameMonoMs: number;
}

export type SnapshotRejectReason =
  | "partial-joint-frame"
  | "unexpected-joint"
  | "non-finite-value";

export type SnapshotResult =
  | {
      readonly accepted: true;
      readonly positionsRad: Readonly<Record<string, number>>;
      readonly frameMonoMs: number;
    }
  | {
      readonly accepted: false;
      readonly reason: SnapshotRejectReason;
      readonly missing: readonly string[];
      readonly unexpected: readonly string[];
    };

// Validate one frame against the full set of joints the loaded URDF declares.
// `expectedJointNames` is derived from the URDF (robot.joints), never hardcoded.
export function acceptSnapshot(
  frame: JointFrame,
  expectedJointNames: readonly string[],
): SnapshotResult {
  const present = new Set(Object.keys(frame.positionsRad));
  const expected = new Set(expectedJointNames);

  const missing = expectedJointNames.filter((name) => !present.has(name));
  const unexpected = Object.keys(frame.positionsRad).filter((name) => !expected.has(name));

  if (missing.length > 0) {
    return { accepted: false, reason: "partial-joint-frame", missing, unexpected };
  }
  if (unexpected.length > 0) {
    return { accepted: false, reason: "unexpected-joint", missing, unexpected };
  }
  for (const name of expectedJointNames) {
    if (!Number.isFinite(frame.positionsRad[name])) {
      return { accepted: false, reason: "non-finite-value", missing: [name], unexpected };
    }
  }
  return {
    accepted: true,
    positionsRad: { ...frame.positionsRad },
    frameMonoMs: frame.frameMonoMs,
  };
}

// One joint of a telemetry frame, as much of it as this module needs. Structural rather than
// the transport's own type: the viewport renders whatever supplies joints in radians, and
// importing the WebSocket reader here would tie the 3D subtree to one carrier.
export interface JointPositionSource {
  readonly name: string;
  readonly positionRad: number;
}

// Build a frame for the loaded model from whatever the backend reported.
//
// The rig reports every joint on the bus — both grippers included — and the model declares the
// joints it has. Taking only the declared ones is not a relaxation of the gate above: what that
// gate is for is a joint the model HAS and the frame does not carry, which still arrives here as
// a missing key and is still refused. What it does mean is that `unexpected-joint` becomes
// unreachable from this path by construction, rather than firing on a gripper the URDF omits.
//
// The unit is not touched. The backend converted through the one CTR-UNIT crossing and these
// are those numbers.
export function jointFrameFor(
  joints: readonly JointPositionSource[],
  expectedJointNames: readonly string[],
  frameMonoMs: number,
): JointFrame {
  const reported = new Map(joints.map((joint) => [joint.name, joint.positionRad]));
  const positionsRad: Record<string, number> = {};
  for (const name of expectedJointNames) {
    const value = reported.get(name);
    if (value !== undefined) {
      positionsRad[name] = value;
    }
  }
  return { positionsRad, frameMonoMs };
}
