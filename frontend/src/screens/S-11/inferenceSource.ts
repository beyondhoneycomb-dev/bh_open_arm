// The inputs S-11 renders from, and an honest offline default. Like every screen, the
// inference/eval screen is a window: the policy-compatibility verdict, the checkpoint<->
// dataset and load-preflight gates, the per-target block matrix and the success-rate report
// all originate in the committed Wave 4B/4C backend. This module names the default source
// and supplies a fixture standing in for a backend that is not attached — the GUI is
// verified against fixtures, never real hardware (WP-G-S11 is AI-offline).
//
// The fixture is deliberately realistic and exercises the load-bearing invariants:
//   - the selected cell is Jetson Orin + GR00T at 30 fps, so the active WP-4B-04 verdict
//     blocks `sync` (fps 30 > 4.6 Hz ceiling, FR-INF-034) and `trt_full_pipeline`
//     (FR-INF-033) — the mode defaults to the valid rtc / DiT-only choice (CG-G-S11g/h);
//   - the fleet spans all four targets: the two Jetson-class edge targets block sync
//     (Orin by ceiling, Nano conservatively), the two RTX-class workstations leave it open
//     to a self-bench, and every IK gate is DEFERRED (per-target hardware absent);
//   - the schema negotiation is a MATCH, so the control UI is unlocked; a test injects a
//     MISMATCH to prove the lock (CG-G-S11a);
//   - the success-rate report is the fully-landed 4C state (N=40 >= 20, meaningful), so the
//     panel shows the point estimate with its Wilson CI; a test injects the N<20 report and
//     the null (2-landing) report (CG-G-S11b/c).

import type {
  ActionQueueTelemetry,
  DeployBlockReason,
  DeploymentTarget,
  InferenceDataSource,
  InferenceScreenData,
  QueueTelemetrySource,
  SuccessRateReport,
  TargetPolicyVerdict,
} from "./types";
import { SELF_BASELINE_KIND } from "./types";

const POLICY_ID = "groot";
const DEFAULT_FPS = 30.0;

// The Orin DiT-only source string, mirrored from the WP-4B-04 verdict provenance so the
// screen renders the backend's own source (FR-TRN-004).
const ORIN_SOURCE = "11 §2.6 (Isaac-GR00T deployment README, Orin DiT-only)";
const JETSON_EDGE_SOURCE = "02c §6.1 (Jetson edge conservative default)";
const NANO_TRT_SOURCE = "02c §6.1 (Jetson Nano conservative default)";

function orinVerdict(): TargetPolicyVerdict {
  const syncReason: DeployBlockReason = {
    code: "FR-INF-034",
    subject: "sync",
    rationale: "fps=30 exceeds the 4.6 Hz sync ceiling; require RTC or async chunking",
    source: ORIN_SOURCE,
  };
  const trtReason: DeployBlockReason = {
    code: "FR-INF-033",
    subject: "trt_full_pipeline",
    rationale:
      "TRT 10.3 cannot compile the backbone engine; trt_full_pipeline is blocked — only " +
      "DiT-only (--inference-mode tensorrt) is allowed",
    source: ORIN_SOURCE,
  };
  return {
    target: "jetson_orin",
    policy: POLICY_ID,
    fps: DEFAULT_FPS,
    expectedHz: 4.6,
    expectedHzSource: ORIN_SOURCE,
    blockedBackends: ["sync"],
    blockedOptimizations: ["trt_full_pipeline"],
    ikGate: "deferred",
    requiredAlternatives: ["rtc", "remote_grpc"],
    reasons: [syncReason, trtReason],
  };
}

function nanoVerdict(): TargetPolicyVerdict {
  const syncReason: DeployBlockReason = {
    code: "FR-INF-034/FR-TRN-004",
    subject: "sync",
    rationale:
      "expected inference frequency is unknown (no 11 §2.6 row) and estimation is " +
      "forbidden; sync is blocked conservatively on this edge target until a self-bench " +
      "establishes the ceiling",
    source: JETSON_EDGE_SOURCE,
  };
  const trtReason: DeployBlockReason = {
    code: "FR-INF-033/FR-TRN-004",
    subject: "trt_full_pipeline",
    rationale:
      "TRT capability is unconfirmed on this target; trt_full_pipeline is blocked " +
      "conservatively until self-confirmed",
    source: NANO_TRT_SOURCE,
  };
  return {
    target: "jetson_nano",
    policy: POLICY_ID,
    fps: DEFAULT_FPS,
    expectedHz: null,
    expectedHzSource: JETSON_EDGE_SOURCE,
    blockedBackends: ["sync"],
    blockedOptimizations: ["trt_full_pipeline"],
    ikGate: "deferred",
    requiredAlternatives: ["rtc", "remote_grpc"],
    reasons: [syncReason, trtReason],
  };
}

// An RTX-class workstation: an unknown ceiling is left to its own self-bench, so sync is
// open here and no optimization is blocked (02c §6.1). IK gate DEFERRED (hardware absent).
function rtxVerdict(target: DeploymentTarget): TargetPolicyVerdict {
  return {
    target,
    policy: POLICY_ID,
    fps: DEFAULT_FPS,
    expectedHz: null,
    expectedHzSource: "02c §6.1 (RTX workstation self-bench)",
    blockedBackends: [],
    blockedOptimizations: [],
    ikGate: "deferred",
    requiredAlternatives: [],
    reasons: [],
  };
}

function fleetVerdicts(): TargetPolicyVerdict[] {
  return [nanoVerdict(), orinVerdict(), rtxVerdict("rtx_5090"), rtxVerdict("rtx_a6000")];
}

// A fully-landed 4C report: N=40 (>= 20, meaningful), 26 successes -> 65% with the Wilson
// 95% interval the backend computed. Off the p̂∈{0,1} boundary, so no Clopper-Pearson.
function successRateReport(): SuccessRateReport {
  return {
    rolloutSetId: "rollout_20260722_gr00t_pickplace",
    checkpoint: { outputDir: "outputs/train/bimanual_pick_place", step: 8000 },
    checkpointHash: "outputs/train/bimanual_pick_place@8000",
    nTrials: 40,
    nSuccess: 26,
    pointEstimate: 0.65,
    ciWilson95: { lower: 0.4951, upper: 0.7787, method: "wilson-95" },
    ciClopperPearson95: null,
    statisticallyMeaningful: true,
    seeds: [11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
    episodeLengthMedian: 214,
    collisionCount: 1,
    torqueLimitHits: 0,
    safetyStopCount: 0,
    inferenceLatencyP95: 41.2,
    failureTagCounts: { grasp_slip: 9, misreach: 5 },
    baselineKind: SELF_BASELINE_KIND,
  };
}

function initialQueue(): ActionQueueTelemetry {
  return {
    backend: "rtc",
    residualActions: 24,
    queueThreshold: 30,
    interpolatorResidual: 0,
    exhaustionCount: 0,
    tick: 512,
  };
}

export function defaultInferenceScreenData(): InferenceScreenData {
  return {
    schema: {
      status: "MATCH",
      clientSchemaVersion: "1.4.0",
      serverSchemaVersion: "1.4.0",
      clientPolicyFeatureVersion: "gr00t-n1.5",
      serverPolicyFeatureVersion: "gr00t-n1.5",
      detail: "스키마·policy feature 버전 일치",
    },
    mode: { deploymentForm: "LOCAL", backend: "rtc", optimization: "tensorrt" },
    policyId: POLICY_ID,
    loop: {
      phase: "RUNNING",
      strategy: "episodic",
      episodeIndex: 3,
      totalEpisodes: 40,
      fps: DEFAULT_FPS,
      controlHz: 30,
      humanInControl: false,
    },
    queue: initialQueue(),
    tasks: [
      { id: "pick_place", prompt: "pick up the block and place it in the bin", active: true },
      { id: "stack", prompt: "stack the red block on the blue block", active: false },
    ],
    takeover: {
      trigger: "keyboard",
      humanInControl: false,
      pauseResumeBinding: "space",
      correctionBinding: "tab",
      uploadBinding: "enter",
    },
    selectedTarget: "jetson_orin",
    fleetVerdicts: fleetVerdicts(),
    policyCompat: { policyId: POLICY_ID, allowed: true, blockingReasons: [] },
    checkpointDataset: { intent: "SERVING", allowed: true, reasons: [] },
    loadPreflight: { allowed: true, refusals: [] },
    successRate: successRateReport(),
  };
}

export function defaultInferenceSource(): InferenceDataSource {
  return { load: defaultInferenceScreenData };
}

// The offline queue-telemetry source: it replays the loaded initial frame and pushes
// nothing more (no timers, no socket — air-gap). A test supplies its own source to drive
// frames and prove the size is live-bound (CG-G-S11f).
export function defaultQueueTelemetrySource(initial: ActionQueueTelemetry): QueueTelemetrySource {
  return {
    initial: () => initial,
    subscribe: () => () => {},
  };
}
