// Backend wire shapes the training screen (WP-G-S10, /training) renders. S-10 is a
// FACADE over the TRN domain (10): the job queue, the source-derived policy
// capabilities (WP-4B-01), the dataset preflight (WP-4A-02), the degenerate-channel
// findings and their forced three-way resolution (WP-4A-03), the local MetricsTracker
// series (WP-4A-01 logstore), the on-disk checkpoint list (WP-4A-01), and the
// eight-element lineage snapshot (WP-4A-05) all originate in the committed Wave 4A/4B
// backend and arrive here as CTR-WS envelope data. This file names those shapes so the
// screen can render them and never re-source, re-compute, or re-decide any of them
// (02c §1.9, 02d §2.2 — the training canon is domain 10). Several invariants are
// structural in the shapes below:
//   - a policy's dimension ceiling is READ from the installed config class (capSource),
//     never a UI constant; the block against a dataset is the backend's, carried with
//     its source so the screen renders the reason (CG-G-S10a/e).
//   - chart series are keyed by the seven MetricsTracker outputs only — no invented
//     key (CG-G-S10b); see metrics.ts for the frozen key set.
//   - every degenerate finding carries its forced EXCLUDE/MANUAL_STATS/PROCEED choice,
//     and training cannot start until each is decided (CG-G-S10 ⑤ / FR-TRN-068).

import type { MetricKey } from "./metrics";

// One training job's lifecycle state — the six-value contract of `02c` §1.1 / backend
// orchestrator/spec.py `JobState`, no more. QUEUED collapses two distinct waits, which
// the screen must keep visible (see `queuedReason`).
export const JOB_STATES = [
  "QUEUED",
  "PREFLIGHT",
  "RUNNING",
  "CANCELLED",
  "FAILED",
  "DONE",
] as const;
export type JobState = (typeof JOB_STATES)[number];

// Why a QUEUED job is waiting. The backend `JobState.QUEUED` comment is explicit that a
// job waits "either for a GPU or for pre-validation"; folding the two into one badge
// would hide a job stuck because no GPU is free (FR-TRN-028). A GPU-absent wait is a
// DISTINCT status the queue view marks, never the same pill as an about-to-preflight
// job (CG-G-S10h). `null` for any non-QUEUED state.
export const QUEUED_REASONS = ["awaiting_gpu", "awaiting_preflight"] as const;
export type QueuedReason = (typeof QUEUED_REASONS)[number];

// One row of the job queue/list (FR-GUI-120), mirrored from backend `JobSpec` plus the
// orchestrator runtime record. The dataset axis is the repo_id + git revision pair
// (`02c` §1.1: a job that dropped the revision would name a moving target).
export interface JobSummary {
  jobId: string;
  name: string;
  policyId: string;
  datasetRepoId: string;
  datasetRevision: string;
  requestedGpus: number;
  state: JobState;
  queuedReason: QueuedReason | null;
  createdIso: string;
  startedIso: string | null;
  endedIso: string | null;
  outputDir: string;
}

// A list/filter/sort request over the job set (backend `JobFilter`). The screen sends
// this as intent; the backend applies it (the screen owns no sort truth).
export interface JobQuery {
  states: readonly JobState[];
  nameContains: string;
  sortBy: "created" | "name" | "state";
  descending: boolean;
}

// One policy's source-derived capability, mirrored from the WP-4B-01 registry (which
// reads it from the installed config class — never a copied constant). `maxStateDim`
// is `null` for a policy with no fixed ceiling (its input width is derived from the
// dataset). `available` is the backend's per-platform verdict (e.g. vqbet blocked);
// the screen renders it and never decides it (CG-G-S10g).
export interface PolicyCapability {
  id: string;
  configClass: string;
  maxStateDim: number | null;
  maxActionDim: number | null;
  capSource: string;
  available: boolean;
  unavailableReason: string | null;
}

// One entry in the policy selector, joining a capability with its block verdict for
// the CURRENTLY selected observation configuration. `blocked`/`blockReason` are the
// WP-4B-01 three-axis matrix result (policy x observation-config x projection) — the
// backend decides, the screen renders the reason with its source (CG-G-S10a/e). When
// the observation config changes, the backend re-emits this list with a policy newly
// blocked or unblocked; the screen does not recompute it.
export interface PolicyOption {
  capability: PolicyCapability;
  blocked: boolean;
  blockReason: PolicyBlockReason | null;
}

// The located reason a policy is blocked for the selected dataset, carrying the SOURCE
// of the ceiling that was exceeded (`02c` §2.1: every blocking reason carries rule_id,
// observed, limit, source). Rendered verbatim so an operator can act on it.
export interface PolicyBlockReason {
  code: string;
  observed: number;
  limit: number;
  source: string;
  human: string;
}

// One hyperparameter field of the policy form (FR-GUI-121). `cliFlag` is shown beside
// the label so the GUI form and the CLI stay legible as one system. `group` ties
// optimizer/scheduler fields together: overriding one field of a preset requires the
// whole group be re-supplied (the backend rejects a half-overridden preset).
export interface HyperparamField {
  key: string;
  label: string;
  cliFlag: string;
  value: string;
  group: "core" | "optimizer" | "scheduler";
}

// One selectable dataset with the stats the form warns on (FR-GUI-122). `episodeCount`
// under `DATASET_MIN_EPISODES` raises a warning (not a block — small data trains, it
// just generalises poorly). `stateDim` is the observation.state width that the policy
// matrix blocks against (48 bimanual vs 32-capped policies).
export interface DatasetOption {
  repoId: string;
  revision: string;
  episodeCount: number;
  frameCount: number;
  stateDim: number;
  actionDim: number;
  useVelocityAndTorque: boolean;
  sizeGb: number;
}

// The VRAM sufficiency check for the selected policy+dataset (FR-GUI-123). When
// `fits` is false the start is DISABLED, `alternatives` names what would fit, and
// `source` records where the requirement estimate came from — a bare "won't fit"
// with no source is not actionable (CG-G-S10e).
export interface VramPreflight {
  fits: boolean;
  requiredGb: number;
  availableGb: number;
  source: string;
  alternatives: readonly string[];
}

// One sample of the training metrics at a step. Keys are the MetricsTracker outputs
// only (see metrics.ts); a partial sample (gpu_mem_gb absent on a CPU run) simply
// omits the key. `Partial` because not every key is present at every step.
export interface MetricSample {
  step: number;
  values: Partial<Record<MetricKey, number>>;
}

// The local, W&B-independent metrics stream (FR-GUI-124). `series` is parsed from the
// orchestrator's own logstore (WP-4A-01) — the loss curve MUST render from this with
// W&B disabled (air-gap, CG-G-S10c). `wandbEnabled` is surfaced so the UI can show the
// air-gapped state honestly; the curve does not depend on it being true.
export interface MetricsStream {
  wandbEnabled: boolean;
  samples: readonly MetricSample[];
  logTail: readonly string[];
}

// One checkpoint on disk (backend `Checkpoint`). `valLoss` may be present, but it is
// NOT the default selection key (CG-G-S10d): offline val-loss does not predict online
// success. `isLast` marks the trainer's atomic `checkpoints/last` symlink target.
export interface CheckpointEntry {
  step: number;
  path: string;
  savedIso: string;
  valLoss: number | null;
  isLast: boolean;
}

// The dataset-preflight verdict the screen renders (backend `PreflightReport`,
// WP-4A-02). BLOCK iff any finding exists; each finding LOCATES its fault (channel,
// and for a state-channel fault the joint + per-motor component) so it is actionable.
export type PreflightVerdict = "PASS" | "BLOCK";
export type PreflightComponent = ".pos" | ".vel" | ".torque";

export interface PreflightFinding {
  code: string;
  channelName: string;
  component: PreflightComponent | null;
  joint: string | null;
  detail: string;
}

export interface PreflightReport {
  verdict: PreflightVerdict;
  findings: readonly PreflightFinding[];
}

// The three ways a degenerate channel may be resolved (backend `DegenerateChoice` /
// FR-TRN-068). Exactly three, and the screen offers all three for every finding — it
// cannot silently drop one.
export const DEGENERATE_CHOICES = ["EXCLUDE", "MANUAL_STATS", "PROCEED"] as const;
export type DegenerateChoice = (typeof DEGENERATE_CHOICES)[number];

// One located degeneracy fault under one normalization mode (backend
// `DegenerateFinding`, WP-4A-03). `amplificationEstimate` is the normalizer gain
// 1/(statistic+eps): O(1) is healthy, ~1e6+ is a channel that will dominate the loss.
export interface DegenerateFinding {
  channelName: string;
  joint: string;
  component: PreflightComponent | null;
  normMode: string;
  statistic: number;
  threshold: number;
  amplificationEstimate: number;
}

// A recorded resolution of one finding (backend `DegenerateDecision`). The screen
// collects these; training cannot start until every finding has one (FR-TRN-068).
export interface DegenerateDecision {
  finding: DegenerateFinding;
  choice: DegenerateChoice;
  rationale: string;
}

// The eight-element lineage snapshot (backend `LineageRecord`, FR-TRN-054 (a)-(h),
// 1:1). The screen renders it and offers the FR-GUI-127 bidirectional query; it never
// synthesises a field. `consumedEpisodes` is the union of the merge maps' target
// indices — the axis the reverse (checkpoint -> episode) query keys on.
export interface LineageDatasetIdentity {
  repoId: string;
  revision: string;
  infoHash: string;
  statsHash: string;
}

export interface LineageObservationConfig {
  useVelocityAndTorque: boolean;
  stateShape: number;
  actionShape: number;
  names: readonly string[];
}

export interface LineageMergeEntry {
  sourceSession: string;
  episodeIndexMap: Readonly<Record<string, number>>;
}

export interface LineageVersionPins {
  codeSha: string;
  lerobotVersion: string;
  containerDigest: string;
}

export interface LineageRecord {
  dataset: LineageDatasetIdentity;
  observation: LineageObservationConfig;
  mergeHistory: readonly LineageMergeEntry[];
  trainConfig: Readonly<Record<string, unknown>>;
  pins: LineageVersionPins;
  degenerateDecisions: readonly DegenerateDecision[];
}

// Whole GPU/VRAM/temperature reading for the metrics panel (FR-GUI-126). MetricsTracker
// emits only gpu_mem_gb; utilisation and temperature come from NVML/nvidia-smi, so they
// are a separate reading the screen renders alongside the chart, never invented.
export interface GpuReading {
  index: number;
  name: string;
  present: boolean;
  utilisationPct: number | null;
  vramUsedGb: number | null;
  vramTotalGb: number | null;
  temperatureC: number | null;
}

// The whole S-10 payload the backend surfaces (over the single WS). It is a snapshot;
// in production a live source pushes fresh snapshots and the AI-offline lane injects a
// deterministic fixture. `gpuPresent` is the host-level fact the GPU-absent QUEUED
// badge reads (CG-G-S10h).
export interface TrainingScreenData {
  jobs: readonly JobSummary[];
  query: JobQuery;
  gpuPresent: boolean;
  gpus: readonly GpuReading[];
  policies: readonly PolicyOption[];
  selectedPolicyId: string;
  hyperparams: readonly HyperparamField[];
  datasets: readonly DatasetOption[];
  selectedDatasetRepoId: string;
  vram: VramPreflight;
  preflight: PreflightReport;
  degenerateFindings: readonly DegenerateFinding[];
  degenerateDecisions: readonly DegenerateDecision[];
  metrics: MetricsStream;
  gpu: GpuReading | null;
  checkpoints: readonly CheckpointEntry[];
  lineage: LineageRecord | null;
}

// The data seam. The default implementation returns an offline fixture; a test injects
// a deterministic snapshot. No implementation here reaches a real backend or opens a
// socket — the single WebSocket is the foundation's (WP-G-01), and the screen never
// constructs one (invariant I-2).
export interface TrainingDataSource {
  load(): TrainingScreenData;
}
