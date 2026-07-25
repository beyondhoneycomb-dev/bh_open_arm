// Backend wire shapes the inference/eval screen (WP-G-S11, /inference) renders. S-11 is
// a FACADE over the INF domain (11): the policy-compatibility matrix (WP-4B-01), the
// checkpoint<->dataset verdict (WP-4B-02), the load preflight (WP-4B-03), the per-target
// inference-path block matrix (WP-4B-04) and the success-rate report (WP-4C-03, the 4C
// increment) all originate in the committed Wave 4B/4C backend and arrive here as CTR-WS
// envelope data. This file names those shapes as TS RENDER SHAPES so the screen can render
// them and never re-source, re-compute, or re-decide any of them (02d §2.2 — the eval
// canon is domain 11). The load-bearing invariants are structural in the shapes below:
//   - a success rate is never a bare point estimate: `pointEstimate` is read only through
//     successRate.ts, always paired with `ciWilson95` (CG-G-S11b); `successRate` is null
//     during the 4B->4C window so the screen shows NO number there (the 2-landing note).
//   - the sync/optimization blocks are the WP-4B-04 verdict's, carried with their source;
//     the screen renders `blockedBackends`/`blockedOptimizations`, never recomputes them
//     (CG-G-S11g/h).
//   - a schema/policy-feature version mismatch is the server's authority; the screen locks
//     its control UI on the reported MISMATCH first (CG-G-S11a).

// The single real-robot rollout engine (11 §2.1). `lerobot-eval` is gym-only (needs an
// `env`, takes no robot) and is NOT a real-robot evaluation path; the harness embeds this
// engine as a library. Named here so the no-lerobot-eval static check (CG-G-S11d) has the
// positive token to assert present, and the negative token to assert absent.
export const ROLLOUT_ENGINE = "lerobot-rollout";

// --- WP-4B-04 deployment targets (02c §2.4, target.py DeploymentTarget) ---
// Exactly the four SPINE §7 fleet targets (03 §5.11 — all four required); A100/H100 are
// an explicit exclusion, never a fifth member.
export const DEPLOYMENT_TARGETS = [
  "jetson_nano",
  "jetson_orin",
  "rtx_5090",
  "rtx_a6000",
] as const;
export type DeploymentTarget = (typeof DEPLOYMENT_TARGETS)[number];

// --- Inference backends (WP-4A-07 backend_kind.py InferenceBackend) ---
// The closed set of three (11 §3.3); the factory dispatches on exactly these.
export const INFERENCE_BACKENDS = ["sync", "rtc", "remote_grpc"] as const;
export type InferenceBackend = (typeof INFERENCE_BACKENDS)[number];

// --- Optimization paths (WP-4B-04 block_matrix.py Optimization) ---
// `trt_full_pipeline` is the only one this matrix ever blocks (FR-INF-033); `tensorrt` is
// the DiT-only path Orin is restricted to; `pytorch` is the eager path.
export const OPTIMIZATIONS = ["trt_full_pipeline", "tensorrt", "pytorch"] as const;
export type Optimization = (typeof OPTIMIZATIONS)[number];

// --- Per-target IK gate status (WP-4B-04 IkGateStatus, 03 §5.11 PG-IK-001) ---
// `deferred` is this band's honest default (per-target hardware absent, AI-offline);
// `fail_blocking` marks a target unsupported (a limit-violating IK solution).
export const IK_GATE_STATUSES = [
  "deferred",
  "pass",
  "retry_with_variant",
  "degraded_accepted",
  "fail_blocking",
  "superseded",
] as const;
export type IkGateStatus = (typeof IK_GATE_STATUSES)[number];

// One reason a backend or optimization path is blocked, with its provenance (WP-4B-04
// BlockReason). Rendered verbatim so an operator sees the requirement (FR-TRN-004).
export interface DeployBlockReason {
  code: string;
  subject: string;
  rationale: string;
  source: string;
}

// The block verdict for one (target, policy, fps) cell (WP-4B-04 TargetPolicyVerdict,
// 02c §2.4). The screen consumes this and derives which options to disable — it never
// recomputes the matrix (CG-G-S11g/h). `blockedBackends` names SYNC when the fps ceiling
// is exceeded; `requiredAlternatives` names the RTC/async paths offered in its place.
export interface TargetPolicyVerdict {
  target: DeploymentTarget;
  policy: string;
  fps: number;
  expectedHz: number | null;
  expectedHzSource: string;
  blockedBackends: readonly InferenceBackend[];
  blockedOptimizations: readonly Optimization[];
  ikGate: IkGateStatus;
  requiredAlternatives: readonly InferenceBackend[];
  reasons: readonly DeployBlockReason[];
}

// The two policy-server deployment forms (11 §2.5 / FR-INF-021). LOCAL is the in-process
// `lerobot-rollout` engine (sync/rtc); ASYNC is the remote gRPC path (policy_server +
// robot_client). Both resolve to ONE start path (CG-G-S11e) — the form is a field of the
// start command, not a fork.
export const DEPLOYMENT_FORMS = ["LOCAL", "ASYNC"] as const;
export type DeploymentForm = (typeof DEPLOYMENT_FORMS)[number];

// The selected inference mode. `deploymentForm` constrains `backend` (LOCAL -> sync/rtc,
// ASYNC -> remote_grpc), and `backend`/`optimization` are gated by the active verdict.
export interface InferenceModeConfig {
  deploymentForm: DeploymentForm;
  backend: InferenceBackend;
  optimization: Optimization;
}

// The schema / policy-feature version negotiation reported by the server (FR-INF-027
// protocol version field). The SERVER is the schema authority; a MISMATCH would be
// rejected as INVALID_ARGUMENT, so the screen renders `status` and locks its control UI
// FIRST (CG-G-S11a) — it does not decide the mismatch itself.
export const SCHEMA_NEGOTIATION_STATES = ["MATCH", "MISMATCH"] as const;
export type SchemaNegotiationStatus = (typeof SCHEMA_NEGOTIATION_STATES)[number];

export interface SchemaNegotiation {
  status: SchemaNegotiationStatus;
  clientSchemaVersion: string;
  serverSchemaVersion: string;
  clientPolicyFeatureVersion: string;
  serverPolicyFeatureVersion: string;
  detail: string;
}

// The rollout strategies (FR-INF-053): base (no record) / sentry / highlight / episodic /
// dagger (HITL). The eval harness runs `--strategy.type=episodic` repeated N times.
export const ROLLOUT_STRATEGIES = ["base", "sentry", "highlight", "episodic", "dagger"] as const;
export type RolloutStrategy = (typeof ROLLOUT_STRATEGIES)[number];

// The inference-loop lifecycle phase the screen renders (rollout/strategies + DAgger FSM,
// 11 §2.2). TAKEOVER is a human holding control; RETURNING is `return_to_initial_position`.
export const LOOP_PHASES = [
  "IDLE",
  "WARMUP",
  "RUNNING",
  "PAUSED",
  "TAKEOVER",
  "RETURNING",
  "STOPPED",
] as const;
export type LoopPhase = (typeof LOOP_PHASES)[number];

// The live inference-loop state (11 §2.2). `controlHz` is `fps × interpolation_multiplier`
// (the effective control rate); `totalEpisodes` is null under duration=0 (24/7 mode).
export interface InferenceLoopState {
  phase: LoopPhase;
  strategy: RolloutStrategy;
  episodeIndex: number;
  totalEpisodes: number | null;
  fps: number;
  controlHz: number;
  humanInControl: boolean;
}

// One frame of action-queue telemetry (CG-G-S11f). `residualActions` is the async chunk
// queue depth (engine.py `queue_residual` / ActionChunkQueue.residual); `queueThreshold`
// is the RTC refill low-watermark; `exhaustionCount` is the QueueMeter starvation count.
// SYNC/REMOTE_GRPC carry residual 0 (no async queue). The screen binds this LIVE and
// re-renders each frame — it is never a value baked at load.
export interface ActionQueueTelemetry {
  backend: InferenceBackend;
  residualActions: number;
  queueThreshold: number;
  interpolatorResidual: number;
  exhaustionCount: number;
  tick: number;
}

// One selectable language task (RolloutConfig.task, 11 §2.7). The switcher sets which is
// active; the screen sends the intent and renders the backend's active task.
export interface InferenceTask {
  id: string;
  prompt: string;
  active: boolean;
}

// How a human takes control during a rollout (FR-INF-048). The trigger and its bindings
// are the backend's config (DAggerKeyboardConfig / DAggerPedalConfig); the screen renders
// them read-only and sends the takeover/release intent — it owns no binding truth.
export const TAKEOVER_TRIGGERS = ["keyboard", "pedal"] as const;
export type TakeoverTrigger = (typeof TAKEOVER_TRIGGERS)[number];

export interface TakeoverControl {
  trigger: TakeoverTrigger;
  humanInControl: boolean;
  pauseResumeBinding: string;
  correctionBinding: string;
  uploadBinding: string;
}

// --- WP-4B-01 policy-compatibility verdict (10 FR-TRN-064/017/004) ---
export interface PolicyBlockingReason {
  ruleId: string;
  fieldName: string;
  observed: number | string;
  limit: number | string;
  source: string;
  message: string;
}

export interface CompatibilityVerdict {
  policyId: string;
  allowed: boolean;
  blockingReasons: readonly PolicyBlockingReason[];
}

// --- WP-4B-02 checkpoint<->dataset verdict (02c §2.2) ---
export const DEPLOYMENT_INTENTS = ["TRAINING", "SERVING"] as const;
export type DeploymentIntent = (typeof DEPLOYMENT_INTENTS)[number];

export interface IncompatibilityReason {
  code: string;
  ruleId: string;
  checkpoint: string;
  dataset: string;
  detail: string;
}

export interface CheckpointDatasetVerdict {
  intent: DeploymentIntent;
  allowed: boolean;
  reasons: readonly IncompatibilityReason[];
}

// --- WP-4B-03 load preflight verdict (02c §2.3, FR-INF-070/037/038) ---
export interface Refusal {
  code: string;
  ruleId: string;
  detail: string;
  observed: string;
  expected: string;
}

export interface LoadVerdict {
  allowed: boolean;
  refusals: readonly Refusal[];
}

// --- WP-4C-03 success-rate report (02c §3.3), the 4C increment ---
export const CI_METHODS = ["wilson-95", "clopper-pearson-95"] as const;
export type CiMethod = (typeof CI_METHODS)[number];

// A binomial proportion interval [lower, upper], both in [0, 1], with the method that
// produced it (WP-4C-03 ConfidenceInterval). The screen renders these bounds — it does not
// compute them (the backend's Wilson/Clopper-Pearson arithmetic is the authority).
export interface ConfidenceInterval {
  lower: number;
  upper: number;
  method: CiMethod;
}

// The lineage identity a report is keyed by (WP-4A-05 CheckpointId).
export interface CheckpointId {
  outputDir: string;
  step: number;
}

// One (rollout set, checkpoint) success-rate report (WP-4C-03 SuccessRateReport). Every
// field the contract names is present; `ciClopperPearson95` is present ONLY on the p̂∈{0,1}
// boundary. `statisticallyMeaningful` equals `nTrials >= N_MIN_MEANINGFUL` and nothing
// else. The screen renders this via successRate.ts, never as a bare point estimate.
export interface SuccessRateReport {
  rolloutSetId: string;
  checkpoint: CheckpointId;
  checkpointHash: string;
  nTrials: number;
  nSuccess: number;
  pointEstimate: number;
  ciWilson95: ConfidenceInterval;
  ciClopperPearson95: ConfidenceInterval | null;
  statisticallyMeaningful: boolean;
  seeds: readonly number[];
  episodeLengthMedian: number;
  collisionCount: number;
  torqueLimitHits: number;
  safetyStopCount: number;
  inferenceLatencyP95: number;
  failureTagCounts: Readonly<Record<string, number>>;
  baselineKind: string;
}

// The N>=20 meaningfulness floor and its rendered flag (WP-4C-03 constants, NFR-PRF-050 /
// FR-SIM-056). Below the floor a report is shown but flagged and no ranking is issued
// (CG-G-S11c). `SELF_BASELINE_KIND` is the only baseline that exists (FR-SIM-059).
export const N_MIN_MEANINGFUL = 20;
export const STATISTICALLY_MEANINGLESS_LABEL = "통계적으로 무의미";
export const SELF_BASELINE_KIND = "self-baseline";

// The whole S-11 payload the backend surfaces (over the single WS). It is a snapshot; in
// production a live source pushes fresh snapshots and the AI-offline lane injects a
// deterministic fixture. `successRate` is null during the 4B->4C landing window — eval
// runs but has no stats yet, and the screen shows NO number there (the 2-landing note).
export interface InferenceScreenData {
  schema: SchemaNegotiation;
  mode: InferenceModeConfig;
  policyId: string;
  loop: InferenceLoopState;
  queue: ActionQueueTelemetry;
  tasks: readonly InferenceTask[];
  takeover: TakeoverControl;
  selectedTarget: DeploymentTarget;
  fleetVerdicts: readonly TargetPolicyVerdict[];
  policyCompat: CompatibilityVerdict;
  checkpointDataset: CheckpointDatasetVerdict;
  loadPreflight: LoadVerdict;
  successRate: SuccessRateReport | null;
}

// The data seam. The default implementation returns an offline fixture; a test injects a
// deterministic snapshot. No implementation here reaches a real backend or opens a socket
// — the single WebSocket is the foundation's (WP-G-01), and the screen never constructs
// one (invariant I-2).
export interface InferenceDataSource {
  load(): InferenceScreenData;
}

// A LIVE seam for the action-queue size (CG-G-S11f). In production the single WS pushes
// queue-telemetry frames and the screen subscribes; each arriving frame re-renders the
// size. The offline default replays the fixture's initial frame and pushes nothing more,
// while a test drives frames through it to prove the size is live-bound, not baked at load.
export interface QueueTelemetrySource {
  initial(): ActionQueueTelemetry;
  subscribe(listener: (telemetry: ActionQueueTelemetry) => void): () => void;
}
