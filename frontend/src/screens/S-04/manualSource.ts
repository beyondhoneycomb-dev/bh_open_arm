// The backend-derived inputs the manual-motion screen renders (WP-G-S04). The
// screen is a window: every number here originates in the MAN domain (04) — joint
// readouts, the active limit set, EE pose, IK tuning, gain profile, freedrive
// compensation state, home profiles, teach points, the control lease. The browser
// converts none of it. In particular position is carried in BOTH rad (F_URDF
// canon) and deg (LeRobot API boundary) because the backend owns that pair
// (CTR-UNIT@v1); the browser never derives one from the other.
//
// This module also supplies an offline default fixture standing in for a backend
// that is not connected — the GUI is verified against fixtures, never real
// hardware (WP-G-S04 is AI-offline). The fixture's numbers are literal backend
// facts (the §2.2 F_URDF limit table, the §2.10 home poses), not computed.

import type { ControlLease, LeaseClock } from "../../mode";
import { defaultViewportSource, type ViewportSource } from "../../viewport";

export type ArmSide = "left" | "right";

// Which limit set the backend is enforcing right now (contract row: the screen
// always shows which is active — v2 URDF rad canon vs the operating soft clamp).
export type LimitSetId = "v2_urdf_canon" | "soft_clamp";

export interface LimitSetStatus {
  activeId: LimitSetId;
  label: string;
}

// One joint's live readout. blockedDirection and nearLimit are BACKEND verdicts
// (FR-MAN-013); the screen renders them and never recomputes "at limit" from the
// position, which would be a second clamp (CG-G-S04a/c).
export interface JointReadout {
  index: number;
  name: string;
  positionRad: number;
  positionDeg: number;
  velocityRadPerSec: number;
  torqueNm: number;
  tempMosC: number;
  tempRotorC: number;
  limitLoRad: number;
  limitHiRad: number;
  nearLimit: boolean;
  blockedDirection: "none" | "positive" | "negative";
}

export type ReferenceFrame = "base" | "tool" | "world";

export interface CartesianFrameInfo {
  frames: readonly ReferenceFrame[];
  activeFrame: ReferenceFrame;
  // base and world share a rotation (base_link world rotation = identity); only
  // the origin differs (FR-MAN-019). The screen states this so an operator does
  // not expect different rotation axes between them.
  baseWorldNote: string;
  translationStepsMm: readonly number[];
  rotationStepsDeg: readonly number[];
}

export interface EeReadout {
  side: ArmSide;
  xMm: number;
  yMm: number;
  zMm: number;
  rollDeg: number;
  pitchDeg: number;
  yawDeg: number;
  controlPointLabel: string;
  // The default control point is the wrist, not the grasp point (FR-MAN-023).
  tcpIsGraspPoint: boolean;
}

export type IkFailureReason = "no_solution" | "limit_reached" | "singularity_near";

export interface IkStatus {
  dampingTikhonov: number;
  lmDamping: number;
  postureCost: number;
  positionCost: number;
  orientationCost: number;
  dt: number;
  maxIters: number;
  solver: string;
  libraryDefaultNote: string;
  singularityNear: boolean;
  lastFailure: { reason: IkFailureReason; message: string } | null;
}

export interface GainProfileStatus {
  activeProfile: string;
  jogProfile: string;
  freedriveProfile: string;
  replayProfile: string;
}

export type FreedrivePath = "A_backdrive" | "B_low_impedance" | "C_gravity_comp";

export interface FreedriveStatus {
  active: boolean;
  side: ArmSide | null;
  gravityCompensated: boolean;
  frictionCompensated: boolean;
  path: FreedrivePath;
}

export interface PreVerifyCheck {
  id: string;
  label: string;
  passed: boolean;
  detail?: string;
}

// Backend trajectory pre-verification (FR-MAN-044/048). The screen renders the
// verdict and disables execute on failure (CG-G-S04h); it runs no collision check.
export interface PreVerifyReport {
  passed: boolean;
  firstViolationIndex: number | null;
  checks: readonly PreVerifyCheck[];
}

export interface HomeProfile {
  id: string;
  name: string;
  targetRad: readonly number[];
  note: string | null;
}

export interface HomeStatus {
  profiles: readonly HomeProfile[];
  activeProfileId: string;
  preVerify: PreVerifyReport;
}

export interface TeachPoint {
  id: string;
  name: string;
  armSide: ArmSide;
  qUrdfRad: readonly number[];
  zeroMethod: string;
  // FR-MAN-040: a point whose zero method disagrees with the robot's current
  // zero record cannot be replayed faithfully.
  zeroMismatch: boolean;
  gainProfile: string;
}

export interface TeachStatus {
  points: readonly TeachPoint[];
  preVerify: PreVerifyReport;
}

export interface DeadmanStatus {
  heartbeatTimeoutMs: number;
  lastBeatMonoClientMs: number;
}

export interface ManualSource {
  side: ArmSide;
  arms: readonly ArmSide[];
  joints: readonly JointReadout[];
  limitSet: LimitSetStatus;
  ee: EeReadout;
  cartesian: CartesianFrameInfo;
  ik: IkStatus;
  gains: GainProfileStatus;
  freedrive: FreedriveStatus;
  home: HomeStatus;
  teach: TeachStatus;
  lease: ControlLease;
  clock: LeaseClock;
  maxLeaseAgeMs: number;
  deadman: DeadmanStatus;
  lastFrameMonoMs: number;
  nowMonoMs: number;
  // FR-MAN-011: the global speed scale starts conservative (<=10%). This is the
  // default selection carried into jog intents; the backend applies the guard.
  speedScalePctDefault: number;
  jogStepSizesDeg: readonly number[];
  viewport: ViewportSource;
}

const RIGHT_JOINT_NAMES = [
  "openarm_right_joint1",
  "openarm_right_joint2",
  "openarm_right_joint3",
  "openarm_right_joint4",
  "openarm_right_joint5",
  "openarm_right_joint6",
  "openarm_right_joint7",
  "openarm_right_finger",
] as const;

// Backend F_URDF limits for the right arm (§2.2). Literal facts, not computed.
interface JointSeed {
  loRad: number;
  hiRad: number;
  positionRad: number;
  positionDeg: number;
}

const RIGHT_JOINT_SEEDS: readonly JointSeed[] = [
  { loRad: -1.3963, hiRad: 3.4907, positionRad: 0, positionDeg: 0 },
  { loRad: -0.17453, hiRad: 3.3161, positionRad: 0, positionDeg: 0 },
  { loRad: -1.5708, hiRad: 1.5708, positionRad: 0, positionDeg: 0 },
  // Home pose J4 = pi/2 (§2.10). Both units are backend facts, stated literally.
  { loRad: 0, hiRad: 2.4435, positionRad: 1.5708, positionDeg: 90 },
  { loRad: -1.5708, hiRad: 1.5708, positionRad: 0, positionDeg: 0 },
  { loRad: -0.7854, hiRad: 0.7854, positionRad: 0, positionDeg: 0 },
  { loRad: -1.5708, hiRad: 1.5708, positionRad: 0, positionDeg: 0 },
  { loRad: -0.7854, hiRad: 0, positionRad: 0, positionDeg: 0 },
];

function demoJoints(): JointReadout[] {
  return RIGHT_JOINT_SEEDS.map((seed, position) => ({
    index: position + 1,
    name: RIGHT_JOINT_NAMES[position],
    positionRad: seed.positionRad,
    positionDeg: seed.positionDeg,
    velocityRadPerSec: 0,
    torqueNm: 0,
    tempMosC: 32,
    tempRotorC: 30,
    limitLoRad: seed.loRad,
    limitHiRad: seed.hiRad,
    nearLimit: false,
    blockedDirection: "none",
  }));
}

// The two home definitions of §2.10, which are physically different poses — hence
// the screen must show the active profile's name and target before executing
// (CG-G-S04j). The all-zero MoveIt pose sits on J4's hard stop and is not usable.
function demoHomeProfiles(): HomeProfile[] {
  return [
    {
      id: "driver_home",
      name: "driver/MuJoCo home (J4 = pi/2)",
      targetRad: [0, 0, 0, 1.5707963, 0, 0, 0, 0],
      note: null,
    },
    {
      id: "moveit_home",
      name: "MoveIt SRDF home (all zero)",
      targetRad: [0, 0, 0, 0, 0, 0, 0, 0],
      note: "J4 하드스톱 자세 — 홈으로 사용 금지 (§2.10)",
    },
  ];
}

function passingPreVerify(): PreVerifyReport {
  return {
    passed: true,
    firstViolationIndex: null,
    checks: [
      { id: "joint_limits", label: "관절 리밋", passed: true },
      { id: "velocity", label: "속도/가속 한계", passed: true },
      { id: "self_collision", label: "자기충돌", passed: true },
      { id: "env_collision", label: "환경충돌", passed: true },
    ],
  };
}

export function defaultManualSource(): ManualSource {
  const lease: ControlLease = {
    sessionId: "offline-session",
    leaseGeneration: 1,
    expiryMonoServer: 5000,
    sequence: 1,
    issuedMonoClient: 900,
  };
  const clock: LeaseClock = { nowMonoServer: 1000, nowMonoClient: 1100 };
  return {
    side: "right",
    arms: ["left", "right"],
    joints: demoJoints(),
    limitSet: {
      activeId: "v2_urdf_canon",
      label: "v2 URDF rad 정본 (F_URDF)",
    },
    ee: {
      side: "right",
      xMm: 401,
      yMm: -153.5,
      zMm: 1120,
      rollDeg: 0,
      pitchDeg: -90,
      yawDeg: 0,
      controlPointLabel: "손목 (ee_base_link)",
      tcpIsGraspPoint: false,
    },
    cartesian: {
      frames: ["base", "tool", "world"],
      activeFrame: "base",
      baseWorldNote: "base와 world는 회전이 동일(단위행렬), 원점만 다름",
      translationStepsMm: [0.1, 1, 10],
      rotationStepsDeg: [0.1, 1, 5],
    },
    ik: {
      dampingTikhonov: 0.1,
      lmDamping: 0.01,
      postureCost: 0.01,
      positionCost: 1.0,
      orientationCost: 1.0,
      dt: 0.1,
      maxIters: 10,
      solver: "daqp",
      libraryDefaultNote: "라이브러리 기본값(damping=0.25, max_iters=5)과 다름 — 상류 VR 튜닝값",
      singularityNear: false,
      lastFailure: null,
    },
    gains: {
      activeProfile: "lerobot_follower",
      jogProfile: "lerobot_follower",
      freedriveProfile: "compliant",
      replayProfile: "stiff",
    },
    freedrive: {
      active: false,
      side: null,
      gravityCompensated: false,
      frictionCompensated: false,
      path: "B_low_impedance",
    },
    home: {
      profiles: demoHomeProfiles(),
      activeProfileId: "driver_home",
      preVerify: passingPreVerify(),
    },
    teach: {
      points: [
        {
          id: "tp-1",
          name: "픽업 접근",
          armSide: "right",
          qUrdfRad: [0, 0.2, 0, 1.5708, 0, 0.1, 0, 0],
          zeroMethod: "jig",
          zeroMismatch: false,
          gainProfile: "stiff",
        },
      ],
      preVerify: passingPreVerify(),
    },
    lease,
    clock,
    maxLeaseAgeMs: 500,
    deadman: {
      heartbeatTimeoutMs: 200,
      lastBeatMonoClientMs: 1000,
    },
    lastFrameMonoMs: 1000,
    nowMonoMs: 1100,
    speedScalePctDefault: 10,
    jogStepSizesDeg: [0.1, 0.5, 1, 5],
    viewport: defaultViewportSource(),
  };
}
