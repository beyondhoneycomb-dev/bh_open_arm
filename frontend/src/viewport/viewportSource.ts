// The inputs the viewport renders from. The viewport is a window: every number it
// shows originates in the backend (provenance, joint frames in radians, the URDF
// link set, the collisions.yaml declaration, the accepted robot version). This
// module names that input bundle and supplies an offline default fixture standing
// in for a backend that is not connected — the GUI is verified against fixtures,
// never real hardware (WP-G-02 is AI-offline).
//
// The default is deliberately honest about its offline state: no frames (so the
// view reads stale, not "fine"), and a collisions.yaml that omits link7 — the
// real, known gap Collision mode must surface (CG-G-02g).

import type { AssetProvenance } from "./loader/provenance";
import type { JointTarget } from "./scene/applyJoints";
import type { JointFrame } from "./state/jointSnapshot";

export interface ViewportSource {
  // Backend-stamped provenance of the served URDF.
  readonly assetProvenance: AssetProvenance;
  // The robot generation the backend declares current; the viewport blocks any
  // asset that does not match it (CG-G-02b). A backend fact, not a GUI constant.
  readonly acceptedRobotVersion: string;
  // Links the loaded URDF declares (reference set for collision coverage).
  readonly urdfLinks: readonly string[];
  // Links collisions.yaml gives a collision geom.
  readonly declaredCollisionLinks: readonly string[];
  // The full joint-name set the URDF declares; a frame must carry every one.
  readonly expectedJointNames: readonly string[];
  // The most recent raw joint frame to gate, or null before any arrives.
  readonly latestFrame: JointFrame | null;
  // Injectable monotonic clock reading (ms) for deterministic stale evaluation.
  readonly nowMonoMs: number;
  // Requested telemetry publish rate (Hz); unset resolves to the 30 Hz default.
  readonly requestedPublishRateHz?: number;
  // The loaded URDF robot handle, or null when none is loaded.
  readonly robotHandle: JointTarget | null;
}

const ARM_SIDES = ["left", "right"] as const;
const JOINTS_PER_ARM = 7;
const LINKS_PER_ARM = 7;
const CURRENT_ROBOT_VERSION = "2.0";

function demoJointNames(): string[] {
  return ARM_SIDES.flatMap((side) =>
    Array.from({ length: JOINTS_PER_ARM }, (_unused, index) => `openarm_${side}_joint${index + 1}`),
  );
}

function demoLinkNames(): string[] {
  return ARM_SIDES.flatMap((side) =>
    Array.from({ length: LINKS_PER_ARM }, (_unused, index) => `openarm_${side}_link${index + 1}`),
  );
}

// collisions.yaml as it stands: every link but link7 carries a collision geom, so
// the end-effector link is the standing gap Collision mode reveals (CG-G-02g).
function demoDeclaredCollisionLinks(): string[] {
  return demoLinkNames().filter((link) => !link.endsWith("link7"));
}

export function defaultViewportSource(): ViewportSource {
  return {
    assetProvenance: {
      source_repo: "openarm_description",
      commit_sha: "0000000000000000000000000000000000000000",
      robot_version: CURRENT_ROBOT_VERSION,
    },
    acceptedRobotVersion: CURRENT_ROBOT_VERSION,
    urdfLinks: demoLinkNames(),
    declaredCollisionLinks: demoDeclaredCollisionLinks(),
    expectedJointNames: demoJointNames(),
    latestFrame: null,
    nowMonoMs: 0,
    robotHandle: null,
  };
}
