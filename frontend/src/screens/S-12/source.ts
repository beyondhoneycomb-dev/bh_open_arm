// The inputs the safety screen renders from, and the intents it emits. The
// screen is a window onto SAF (12): every number it shows — the friction gate
// outcome, the forced detection status, the applied reaction mode, the residual
// samples and their thresholds, the backend contact list, the injected walls,
// the event ring buffer — originates in the backend. The screen sends user
// intent (pick a reaction, inject a wall, acknowledge a latch) and never decides
// domain truth: no clamps, no unit conversion, no collision judgement.
//
// This WP is AI-offline and verified against fixtures, so `defaultSafetyScreenSource`
// stands in for a backend that is not connected, exactly as the viewport's
// `defaultViewportSource` does. The default is honest about reality: PG-FRIC-001
// is NOT passed and torque observation is OFF, so detection is forced DISABLED —
// the standing-banner state CG-G-S12b exercises.

import type { ContactSeverity } from "./contactSeverity";
import type { FrictionGateOutcome } from "./detectionGate";
import type { JointResidual } from "./residualGeometry";
import type { ReactionMode } from "./reactionPolicy";

export type WallShape = "box" | "plane";

export interface VirtualWall {
  id: string;
  label: string;
  shape: WallShape;
  // Center position in meters, in the backend's ROS frame. The GUI does not
  // transform frames — it hands these numbers to the geom injector as given.
  center: readonly [number, number, number];
  // Box half-extents in meters (box shape).
  halfExtents: readonly [number, number, number];
  // Plane unit normal (plane shape).
  normal: readonly [number, number, number];
  enabled: boolean;
}

// The spec the wall editor sends to the backend geom injector. A new wall omits
// the id; the backend assigns it.
export interface VirtualWallSpec {
  id?: string;
  label: string;
  shape: WallShape;
  center: readonly [number, number, number];
  halfExtents: readonly [number, number, number];
  normal: readonly [number, number, number];
  enabled: boolean;
}

export interface ContactRecord {
  id: string;
  // The two geoms MuJoCo reports in contact (backend names).
  geom1: string;
  geom2: string;
  // Signed penetration depth in meters (negative = penetrating). A backend fact.
  distMeters: number;
  // The backend collision margin for this contact (FR-SAF-011).
  marginMeters: number;
  // Contact point in meters, backend frame, for display only.
  point: readonly [number, number, number];
}

export interface SafetyEvent {
  id: string;
  tMonoMs: number;
  // Backend latch-cause string (§2.13).
  cause: string;
  // The reaction the backend applied when this event latched.
  reaction: ReactionMode;
  // Whether the latch is still held; a held latch needs an explicit ack
  // (FR-SAF-043 latch_until_ack).
  latched: boolean;
  // Joints whose residual breached, backend-provided.
  joints: readonly string[];
}

export type DetectionStatus = "DISABLED" | "ARMED" | "LATCHED";

export interface SafetyScreenSource {
  // PG-FRIC-001 outcome (backend). Detection cannot be enabled unless passed.
  readonly frictionGate: FrictionGateOutcome;
  // use_velocity_and_torque coupled flag (FR-SAF-072).
  readonly torqueObservationEnabled: boolean;
  // The status the backend currently holds detection at.
  readonly detectionStatus: DetectionStatus;
  // The reaction mode the backend currently applies, or null if none reported.
  readonly reactionMode: ReactionMode | null;
  // Per-joint residual timeseries with their backend thresholds.
  readonly residuals: readonly JointResidual[];
  // The backend contact list (walls + cell geoms) from the collision check.
  readonly contacts: readonly ContactRecord[];
  // The virtual walls currently injected into the MJCF scene.
  readonly walls: readonly VirtualWall[];
  // The collision-event ring buffer (FR-SAF-065), newest first.
  readonly events: readonly SafetyEvent[];
  // Injectable monotonic clock reading (ms) for deterministic rendering.
  readonly nowMonoMs: number;
}

// User intents the screen emits. Each is a control-frame command the backend
// applies; the defaults are no-ops so the offline screen is inert but complete.
export interface SafetyScreenIntents {
  // Ask the backend to apply a reaction mode (backend enforces; screen renders).
  onSelectReaction: (mode: ReactionMode) => void;
  // Ask the backend to arm detection. Only reachable when the gate permits.
  onEnableDetection: () => void;
  // Send a wall spec to the backend geom injector — the ONLY path a wall edit
  // reaches the scene (CG-G-S12d).
  onInjectWall: (spec: VirtualWallSpec) => void;
  // Ask the backend to remove an injected wall.
  onRemoveWall: (id: string) => void;
  // Acknowledge a latched event so the backend may clear the latch (FR-SAF-043).
  onAcknowledgeEvent: (id: string) => void;
}

export function noopIntents(): SafetyScreenIntents {
  return {
    onSelectReaction: () => {},
    onEnableDetection: () => {},
    onInjectWall: () => {},
    onRemoveWall: () => {},
    onAcknowledgeEvent: () => {},
  };
}

const RESIDUAL_SAMPLE_COUNT = 48;
// URDF effort limits for J1..J3 (§2.5); the residual threshold's design ceiling.
const DEMO_EFFORT_LIMITS_NM = [40, 40, 27] as const;
// Illustrative per-joint thresholds well inside the effort limits.
const DEMO_THRESHOLDS_NM = [4, 4, 2.7] as const;

// A deterministic triangle wave in [-1, 1], period 12 samples. Kept to plain
// modulo arithmetic so the fixture carries no angle math of any kind.
const TRIANGLE_PERIOD = 12;
function triangleWave(index: number): number {
  const position = (index % TRIANGLE_PERIOD) / TRIANGLE_PERIOD;
  return position < 0.5 ? position * 4 - 1 : 3 - position * 4;
}

function demoResidual(jointIndex: number, breaching: boolean): JointResidual {
  const effortLimitNm = DEMO_EFFORT_LIMITS_NM[jointIndex];
  const thresholdNm = DEMO_THRESHOLDS_NM[jointIndex];
  const samples = Array.from({ length: RESIDUAL_SAMPLE_COUNT }, (_unused, index) => {
    const base = triangleWave(index) * (thresholdNm * 0.4);
    const spike = breaching && index > RESIDUAL_SAMPLE_COUNT - 6 ? thresholdNm * 1.6 : 0;
    return { tMonoMs: index * 20, valueNm: base + spike };
  });
  return {
    jointName: `openarm_left_joint${jointIndex + 1}`,
    samples,
    thresholdNm,
    effortLimitNm,
  };
}

// Standing offline fixture. The gates read from it directly, so its state is the
// real, known one: friction unidentified, torque observation off, detection
// forced DISABLED, reaction defaulted to STOP_HOLD.
export function defaultSafetyScreenSource(): SafetyScreenSource {
  return {
    frictionGate: "not_passed",
    torqueObservationEnabled: false,
    detectionStatus: "DISABLED",
    reactionMode: "STOP_HOLD",
    residuals: [demoResidual(0, false), demoResidual(1, true), demoResidual(2, false)],
    contacts: [
      {
        id: "c-intrusion",
        geom1: "openarm_left_link6_col",
        geom2: "cell_front_wall_col",
        distMeters: -0.004,
        marginMeters: 0.02,
        point: [0.31, 0.12, 0.44],
      },
      {
        id: "c-imminent",
        geom1: "openarm_left_link4_col",
        geom2: "vwall_keepout_a",
        distMeters: 0.011,
        marginMeters: 0.02,
        point: [0.22, -0.05, 0.51],
      },
      {
        id: "c-clear",
        geom1: "openarm_right_link3_col",
        geom2: "cell_table_col",
        distMeters: 0.08,
        marginMeters: 0.02,
        point: [-0.18, 0.2, 0.3],
      },
    ],
    walls: [
      {
        id: "vwall_keepout_a",
        label: "작업자 금지영역 A",
        shape: "box",
        center: [0.2, 0.0, 0.5],
        halfExtents: [0.1, 0.3, 0.4],
        normal: [0, 0, 1],
        enabled: true,
      },
    ],
    events: [
      {
        id: "e-1",
        tMonoMs: 12_000,
        cause: "residual breach: joint2 (r > threshold, 3-tick debounce)",
        reaction: "STOP_HOLD",
        latched: true,
        joints: ["openarm_left_joint2"],
      },
    ],
    nowMonoMs: 13_000,
  };
}

// Re-export the display-severity type so consumers import the source surface in
// one place.
export type { ContactSeverity };
