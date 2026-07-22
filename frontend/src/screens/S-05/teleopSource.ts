// The backend-derived inputs the teleop screen renders (WP-G-S05). The screen is
// a window onto the TEL domain (05): the alignment state machine, the clutch, the
// delta scales, the One-Euro smoother, the C-Lat instrumentation, the VR link
// watchdog, the WebXR entry point and the PG-VR-001 gate all live in the backend
// `Teleoperator` / safety gate. Every number here originates there; the browser
// derives none of it (no deg<->rad, no clutch-threshold decision, no smoother
// filter math, no self-clamp) — that is the §0.2 facade rule.
//
// This module names that input bundle and supplies an offline default fixture
// standing in for a backend that is not connected (WP-G-S05 is AI-offline). Every
// literal in the fixture is a backend fact stated once (the `05` §3 parameter
// table defaults, the `05` §2.5 C-Lat stage budget, the `05` §4.1 state machine),
// not a value the browser computes.

import { defaultViewportSource, type ViewportSource } from "../../viewport";

import type { TeleopStateId } from "./stateMachine";

export type TeleopArm = "left" | "right";

// The alignment verdict the backend `AlignRamp` renders (`05` §4.1 S3, FR-TEL-083).
// `converged` is `max |q_target - q| < threshold`, decided backend-side; the screen
// renders it and gates the follow affordance on it (CG-G-S05b) — it recomputes
// nothing.
export interface AlignmentStatus {
  currentState: TeleopStateId;
  converged: boolean;
  thresholdRad: number;
  perJointErrorRad: readonly number[];
  maxErrorRad: number;
}

// The clutch (deadman) state the backend `ClutchGate` holds (FR-TEL-030/031). The
// re-grip delta is the invariant this screen must show honestly: releasing discards
// the reference and re-gripping re-captures it, so the backend reports both deltas
// as exactly zero at the re-grip instant (`05` §4.2 forbidden transition 7). The
// screen renders `regripDelta*`; it never measures a delta itself.
export interface ClutchStatus {
  engaged: boolean;
  referenceLatched: boolean;
  thresholdGrip: number;
  gripValue: number;
  regripDeltaPosMm: number;
  regripDeltaRotDeg: number;
}

// The two mapping scales, independent by contract: joint6's ±45° limit forces the
// rotation channel to narrow without shrinking translation, so they never share a
// value (FR-TEL-029/033). Ranges are the backend-declared adjustable bands (`05`
// §3), shown as the slider bounds — a display affordance, not a self-clamp.
export interface ScaleStatus {
  positionScale: number;
  positionScaleMin: number;
  positionScaleMax: number;
  rotationScale: number;
  rotationScaleMin: number;
  rotationScaleMax: number;
}

// The One-Euro smoother setting the backend has applied, with the theoretical phase
// lag `tau` the backend computes from the current cutoff (NFR-PRF-018, `05` §2.5 ②).
// `tauMs` is a backend value the screen renders alongside the FR-GUI-106 formula
// label; the browser does not derive it.
export interface SmootherApplied {
  minCutoffHz: number;
  beta: number;
  dCutoff: number;
  tauMs: number;
}

export interface SmootherStatus {
  applied: SmootherApplied;
  minCutoffMin: number;
  minCutoffMax: number;
  betaMin: number;
  betaMax: number;
  dCutoffMin: number;
  dCutoffMax: number;
}

// How a C-Lat stage value is known. The `05` §2.5 budget is explicit that some
// stages are measured, some computed, some unknown, and one (the smoother) is a
// design variable — the screen must not flatten that distinction into a single
// number.
export type CLatStageKind = "measured" | "computed" | "unknown" | "design_variable" | "eliminated";

export interface CLatStage {
  marker: string;
  label: string;
  valueMs: number | null;
  kind: CLatStageKind;
}

// The control-channel latency instrumentation (`05` §2.5, M-3, NFR-PRF-014/018).
// C-Lat is the control channel ONLY — the headset-internal latency it cannot see is
// the standing note the C-Lat view carries (CG-G-S05a). `lowerBoundMs` is the
// backend's startup self-calculation (NFR-PRF-018); the totals are its measured
// aggregates, or null when instrumentation is not running.
export interface CLatStatus {
  stages: readonly CLatStage[];
  lowerBoundMs: number;
  totalP50Ms: number | null;
  totalP99Ms: number | null;
}

export type TrackingValidity = "OK" | "STALE" | "INVALID";
export type LinkHealth = "live" | "lost";

// The VR link watchdog (FR-TEL-081/094). `linkHealth` is the backend
// `LinkHeartbeat.health` verdict; STALE is a lost link because `treatStaleAsLost`
// is frozen true. Every field is a backend reading the screen displays.
export interface WatchdogStatus {
  linkHealth: LinkHealth;
  trackingValidity: TrackingValidity;
  treatStaleAsLost: boolean;
  heartbeatTimeoutMs: number;
  heartbeatTimeoutMin: number;
  heartbeatTimeoutMax: number;
  lastFrameAgeMs: number | null;
  measuredHz: number | null;
  jitterMs: number | null;
}

export type VrGateStatus = "pending" | "passed" | "failed";

// PG-VR-001 (WP-3C-04): a HARDWARE gate that decides whether the native Quest APK
// path is usable. It is not built yet, so its verdict arrives as WS state that is
// currently "pending". The screen renders that pending state graphically and never
// fabricates a verdict (§ graceful 3C-gate handling); a real `failed` drives the
// WebXR fallback (WP-3B-08).
export interface VrGate {
  id: "PG-VR-001";
  status: VrGateStatus;
  note: string;
}

export type VrTransport = "apk_udp" | "webxr";
export type SessionMode = "bimanual" | "right" | "left";

export interface VrSessionStatus {
  active: boolean;
  mode: SessionMode;
  transport: VrTransport;
  udpPort: number;
  headsetConnected: boolean;
  referenceSpace: string;
  poseSpace: string;
  controllerProfiles: readonly string[];
}

// The WebXR entry point config (WP-3B-08, FR-GUI-005). A separate HTTPS component
// from the SPA — HTTPS is mandatory (WebXR needs a secure context) and the port is
// distinct from the SPA-serving port. These are backend config facts the screen
// reads and displays; the browser opens no socket here.
export interface WebxrEntry {
  scheme: "https";
  host: string;
  port: number;
  sessionMode: string;
  tlsCertPath: string;
  tlsKeyPath: string;
  fallbackProfileChain: readonly string[];
}

// The leader (VR controller) side of the leader-vs-follower 3D view. The follower
// is the robot the shared viewport renders; the leader is the controller pose whose
// tracking validity gates whether following is even possible.
export interface LeaderStatus {
  arm: TeleopArm;
  trackingValidity: TrackingValidity;
  gripValue: number;
}

export interface TeleopSource {
  arms: readonly TeleopArm[];
  jointNames: readonly string[];
  alignment: AlignmentStatus;
  clutch: ClutchStatus;
  scale: ScaleStatus;
  smoother: SmootherStatus;
  cLat: CLatStatus;
  watchdog: WatchdogStatus;
  session: VrSessionStatus;
  vrGate: VrGate;
  webxr: WebxrEntry;
  leaders: readonly LeaderStatus[];
  viewport: ViewportSource;
}

const RIGHT_ARM_JOINT_NAMES = [
  "openarm_right_joint1",
  "openarm_right_joint2",
  "openarm_right_joint3",
  "openarm_right_joint4",
  "openarm_right_joint5",
  "openarm_right_joint6",
  "openarm_right_joint7",
] as const;

// The `05` §2.5 C-Lat stage budget stated once. Values are the doc's own figures
// (measured / computed / unknown / eliminated / design-variable); ② carries the
// applied smoother's theoretical lag, which the backend recomputes when the cutoff
// changes, so the fixture states the upstream-constant default (min_cutoff 2.0 ->
// ~79.6 ms).
function demoCLatStages(): CLatStage[] {
  return [
    { marker: "①", label: "손 이동 → Quest 포즈 확정 (72 Hz 1프레임)", valueMs: 13.9, kind: "computed" },
    { marker: "②", label: "One-Euro 필터 위상 지연 (설계 변수, 스무더 설정 종속)", valueMs: 79.6, kind: "design_variable" },
    { marker: "③", label: "헤드셋 → PC 전송 (Wi-Fi, UDP :5006)", valueMs: null, kind: "unknown" },
    { marker: "④", label: "IPC (단일 프로세스 — 함수 호출)", valueMs: 0, kind: "eliminated" },
    { marker: "⑤", label: "IK solve (openarm_control)", valueMs: 0.355, kind: "measured" },
    { marker: "⑥", label: "안전 필터 (클램프·점프 가드)", valueMs: null, kind: "unknown" },
    { marker: "⑦", label: "send_action() → CAN 프레임 송신", valueMs: 0.4, kind: "computed" },
    { marker: "⑧", label: "모터(DAMIAO) 명령 → 축 반응", valueMs: null, kind: "unknown" },
  ];
}

// The offline default is deliberately honest about not being connected: the link is
// LOST (so the watchdog reads lost, not "fine"), no session is active, and PG-VR-001
// is `pending` (the HW gate has not landed — the screen shows pending, not a faked
// pass). The clutch is released with zero re-grip deltas, which is the correct
// resting truth.
export function defaultTeleopSource(): TeleopSource {
  return {
    arms: ["right"],
    jointNames: [...RIGHT_ARM_JOINT_NAMES],
    alignment: {
      currentState: "S2",
      converged: false,
      thresholdRad: 0.1,
      perJointErrorRad: [0.32, 0.18, 0.09, 0.41, 0.05, 0.12, 0.03],
      maxErrorRad: 0.41,
    },
    clutch: {
      engaged: false,
      referenceLatched: false,
      thresholdGrip: 0.9,
      gripValue: 0.0,
      regripDeltaPosMm: 0,
      regripDeltaRotDeg: 0,
    },
    scale: {
      positionScale: 0.8,
      positionScaleMin: 0.1,
      positionScaleMax: 2.0,
      rotationScale: 1.0,
      rotationScaleMin: 0.0,
      rotationScaleMax: 1.0,
    },
    smoother: {
      applied: { minCutoffHz: 2.0, beta: 0.04, dCutoff: 1.5, tauMs: 79.6 },
      minCutoffMin: 0.1,
      minCutoffMax: 20.0,
      betaMin: 0.0,
      betaMax: 1.0,
      dCutoffMin: 0.1,
      dCutoffMax: 10.0,
    },
    cLat: {
      stages: demoCLatStages(),
      lowerBoundMs: 94.3,
      totalP50Ms: null,
      totalP99Ms: null,
    },
    watchdog: {
      linkHealth: "lost",
      trackingValidity: "INVALID",
      treatStaleAsLost: true,
      heartbeatTimeoutMs: 100,
      heartbeatTimeoutMin: 30,
      heartbeatTimeoutMax: 500,
      lastFrameAgeMs: null,
      measuredHz: null,
      jitterMs: null,
    },
    session: {
      active: false,
      mode: "right",
      transport: "apk_udp",
      udpPort: 5006,
      headsetConnected: false,
      referenceSpace: "viewer",
      poseSpace: "gripSpace",
      controllerProfiles: [],
    },
    vrGate: {
      id: "PG-VR-001",
      status: "pending",
      note: "HW 게이트(WP-3C-04) 미착지 — 검증 대기",
    },
    webxr: {
      scheme: "https",
      host: "0.0.0.0",
      port: 8443,
      sessionMode: "immersive-ar",
      tlsCertPath: "/etc/openarm/tls/webxr.crt",
      tlsKeyPath: "/etc/openarm/tls/webxr.key",
      fallbackProfileChain: [
        "meta-quest-touch-plus",
        "meta-quest-touch-plus-v2",
        "oculus-touch-v3",
        "generic-trigger-squeeze-thumbstick",
      ],
    },
    leaders: [{ arm: "right", trackingValidity: "INVALID", gripValue: 0.0 }],
    viewport: defaultViewportSource(),
  };
}
