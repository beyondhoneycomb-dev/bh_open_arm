// The inputs S-10 renders from, and an honest offline default. Like every screen, the
// training screen is a window: the job queue, the source-derived policy capabilities,
// the dataset preflight, the degenerate findings, the local metrics, the checkpoints and
// the lineage snapshot all originate in the committed Wave 4A/4B backend. This module
// names the default source and supplies a fixture standing in for a backend that is not
// attached — the GUI is verified against fixtures, never real hardware (WP-G-S10 is
// AI-offline).
//
// The fixture is deliberately realistic and honest:
//   - the selected dataset is bimanual + use_velocity_and_torque (48-dim), so the
//     32-capped policies come back BLOCKED with their source and GR00T (132) allowed —
//     the three-axis matrix result, not a UI guess (CG-G-S10a/e);
//   - a second dataset is pos-only (16-dim) and under the 50-episode floor, so the form
//     shows both the shape the matrix survives and the small-data warning (CG-G-S10f);
//   - one degenerate finding is UNDECIDED, so training is start-blocked until the
//     operator makes the three-way choice (CG-G-S10 ⑤ / FR-TRN-068);
//   - the queue carries a GPU-absent QUEUED job distinct from an about-to-preflight one
//     (CG-G-S10h);
//   - the metrics stream has W&B disabled and still carries a local loss curve
//     (CG-G-S10c), keyed only by the seven MetricsTracker outputs (CG-G-S10b);
//   - the checkpoints include a non-latest minimum-val-loss entry, so the default (the
//     latest) provably is not the val-loss minimum (CG-G-S10d).
//
// No policy name is authored here: the policy list is derived from the registry snapshot
// (policyRegistry.ts), and the default selection is the first non-blocked option's id.

import { loadPolicyCapabilities, resolvePolicyOptions, snapshotLerobotVersion } from "./policyRegistry";
import type {
  CheckpointEntry,
  DatasetOption,
  DegenerateFinding,
  GpuReading,
  HyperparamField,
  JobSummary,
  LineageRecord,
  MetricSample,
  MetricsStream,
  PolicyOption,
  PreflightReport,
  TrainingDataSource,
  TrainingScreenData,
  VramPreflight,
} from "./types";

const POSITION_SUFFIX = ".pos";
const VELOCITY_SUFFIX = ".vel";
const TORQUE_SUFFIX = ".torque";
const ARMS = ["left", "right"] as const;
const JOINTS_PER_ARM = 8;

// The observation.state channel names for a bimanual arm pair, in CTR-REC@v1 order:
// .pos always, then .vel/.torque per joint under use_velocity_and_torque.
function stateNames(useVelocityAndTorque: boolean): string[] {
  const names: string[] = [];
  for (const arm of ARMS) {
    for (let joint = 1; joint <= JOINTS_PER_ARM; joint += 1) {
      const base = `${arm}_joint_${joint}`;
      names.push(`${base}${POSITION_SUFFIX}`);
      if (useVelocityAndTorque) {
        names.push(`${base}${VELOCITY_SUFFIX}`);
        names.push(`${base}${TORQUE_SUFFIX}`);
      }
    }
  }
  return names;
}

// action is position only — one .pos channel per joint per arm.
function actionNames(): string[] {
  const names: string[] = [];
  for (const arm of ARMS) {
    for (let joint = 1; joint <= JOINTS_PER_ARM; joint += 1) {
      names.push(`${arm}_joint_${joint}${POSITION_SUFFIX}`);
    }
  }
  return names;
}

const BIMANUAL_UVT_REPO = "openarm/bimanual_pick_place_20260720_101500";
const POS_ONLY_REPO = "openarm/bimanual_stack_20260715_143000";

function bimanualDataset(): DatasetOption {
  return {
    repoId: BIMANUAL_UVT_REPO,
    revision: "v3.0",
    episodeCount: 180,
    frameCount: 54_000,
    stateDim: stateNames(true).length,
    actionDim: actionNames().length,
    useVelocityAndTorque: true,
    sizeGb: 12.4,
  };
}

function posOnlyDataset(): DatasetOption {
  return {
    repoId: POS_ONLY_REPO,
    revision: "v3.0",
    episodeCount: 40,
    frameCount: 12_000,
    stateDim: stateNames(false).length,
    actionDim: actionNames().length,
    useVelocityAndTorque: false,
    sizeGb: 2.1,
  };
}

function policyOptionsFor(dataset: DatasetOption): PolicyOption[] {
  return resolvePolicyOptions(loadPolicyCapabilities(), dataset);
}

// The first non-blocked policy id for the selected dataset — GR00T for the 48-dim case,
// derived from data so no policy name is authored (CG-G-S10a).
function defaultPolicyId(options: readonly PolicyOption[]): string {
  const open = options.find((option) => !option.blocked);
  return (open ?? options[0]).capability.id;
}

function hyperparams(): HyperparamField[] {
  return [
    { key: "steps", label: "학습 스텝", cliFlag: "--steps", value: "200000", group: "core" },
    { key: "batch_size", label: "배치 크기", cliFlag: "--batch_size", value: "8", group: "core" },
    {
      key: "optimizer.lr",
      label: "학습률",
      cliFlag: "--optimizer.lr",
      value: "1e-4",
      group: "optimizer",
    },
    {
      key: "optimizer.weight_decay",
      label: "weight decay",
      cliFlag: "--optimizer.weight_decay",
      value: "1e-6",
      group: "optimizer",
    },
    {
      key: "scheduler.num_warmup_steps",
      label: "warmup 스텝",
      cliFlag: "--scheduler.num_warmup_steps",
      value: "2000",
      group: "scheduler",
    },
  ];
}

// VRAM preflight for the selected policy+dataset, carrying the SOURCE of the estimate
// (CG-G-S10e). The default fits on a 16 GB card; a test injects the exceeded case.
function vramPreflight(): VramPreflight {
  return {
    fits: true,
    requiredGb: 14.2,
    availableGb: 16.0,
    source: "nvidia-smi (RTX 5080, 16 GB) vs. selected-policy LoRA train estimate (WP-4A-01 preflight)",
    alternatives: [],
  };
}

// Dataset preflight PASSES here so the only start blocker is the undecided degenerate
// finding; a test injects a BLOCK report to exercise the located-finding renderer.
function preflightReport(): PreflightReport {
  return { verdict: "PASS", findings: [] };
}

// One genuinely degenerate channel: a wrist joint whose torque barely moved across the
// session, so MEAN_STD normalisation would amplify its noise ~1e7x. UNDECIDED, so the
// start gate holds until the operator makes the three-way choice (FR-TRN-068).
function degenerateFindings(): DegenerateFinding[] {
  return [
    {
      channelName: `right_joint_7${TORQUE_SUFFIX}`,
      joint: "right_joint_7",
      component: TORQUE_SUFFIX,
      normMode: "MEAN_STD",
      statistic: 3.1e-7,
      threshold: 1e-4,
      amplificationEstimate: 3.2e6,
    },
  ];
}

function metricSamples(): MetricSample[] {
  const losses = [1.82, 1.21, 0.94, 0.77, 0.63, 0.55, 0.49, 0.44];
  return losses.map((loss, index) => {
    const step = (index + 1) * 1000;
    const values: MetricSample["values"] = {
      loss,
      grad_norm: Number((2.4 - index * 0.18).toFixed(3)),
      lr: Number((1e-4 * (1 - index / 40)).toExponential(2)),
      samples_per_s: 96 + index,
      update_s: Number((0.42 - index * 0.005).toFixed(3)),
      dataloading_s: Number((0.08 + (index % 3) * 0.004).toFixed(3)),
      gpu_mem_gb: Number((13.6 + index * 0.05).toFixed(2)),
    };
    return { step, values };
  });
}

function metricsStream(): MetricsStream {
  return {
    wandbEnabled: false,
    samples: metricSamples(),
    logTail: [
      "INFO step=8000 loss=0.440 grad_norm=1.14 lr=8.0e-05 smp/s=103 updt_s=0.385 data_s=0.088 mem_gb=13.95",
      "INFO checkpoint saved: outputs/train/bimanual_pick_place/checkpoints/008000",
      "INFO W&B disabled (air-gapped host); metrics persisted to local logstore only",
    ],
  };
}

function gpuReading(): GpuReading {
  return {
    index: 0,
    name: "NVIDIA GeForce RTX 5080",
    present: true,
    utilisationPct: 97,
    vramUsedGb: 13.95,
    vramTotalGb: 16.0,
    temperatureC: 71,
  };
}

// Checkpoints: the minimum val loss is at step 6000 (a NON-latest entry), while the
// latest is 8000 and carries the `last` symlink. So the default selection (latest)
// provably differs from the val-loss minimum (CG-G-S10d).
function checkpoints(): CheckpointEntry[] {
  return [
    {
      step: 2000,
      path: "outputs/train/bimanual_pick_place/checkpoints/002000",
      savedIso: "2026-07-20T11:05:00Z",
      valLoss: 0.71,
      isLast: false,
    },
    {
      step: 4000,
      path: "outputs/train/bimanual_pick_place/checkpoints/004000",
      savedIso: "2026-07-20T11:41:00Z",
      valLoss: 0.58,
      isLast: false,
    },
    {
      step: 6000,
      path: "outputs/train/bimanual_pick_place/checkpoints/006000",
      savedIso: "2026-07-20T12:18:00Z",
      valLoss: 0.51,
      isLast: false,
    },
    {
      step: 8000,
      path: "outputs/train/bimanual_pick_place/checkpoints/008000",
      savedIso: "2026-07-20T12:55:00Z",
      valLoss: 0.55,
      isLast: true,
    },
  ];
}

function jobs(selectedPolicyId: string): JobSummary[] {
  const bimanual = bimanualDataset();
  return [
    {
      jobId: "job_20260720_101500",
      name: "bimanual pick-place (LoRA, run A)",
      policyId: selectedPolicyId,
      datasetRepoId: bimanual.repoId,
      datasetRevision: bimanual.revision,
      requestedGpus: 1,
      state: "RUNNING",
      queuedReason: null,
      createdIso: "2026-07-20T10:15:00Z",
      startedIso: "2026-07-20T10:16:12Z",
      endedIso: null,
      outputDir: "outputs/train/bimanual_pick_place",
    },
    {
      jobId: "job_20260720_113000",
      name: "bimanual pick-place (retry, larger batch)",
      policyId: selectedPolicyId,
      datasetRepoId: bimanual.repoId,
      datasetRevision: bimanual.revision,
      requestedGpus: 1,
      state: "QUEUED",
      queuedReason: "awaiting_gpu",
      createdIso: "2026-07-20T11:30:00Z",
      startedIso: null,
      endedIso: null,
      outputDir: "outputs/train/bimanual_pick_place_retry",
    },
    {
      jobId: "job_20260720_114500",
      name: "pos-only stack (sanity)",
      policyId: selectedPolicyId,
      datasetRepoId: POS_ONLY_REPO,
      datasetRevision: "v3.0",
      requestedGpus: 1,
      state: "QUEUED",
      queuedReason: "awaiting_preflight",
      createdIso: "2026-07-20T11:45:00Z",
      startedIso: null,
      endedIso: null,
      outputDir: "outputs/train/pos_only_stack",
    },
    {
      jobId: "job_20260719_090000",
      name: "bimanual pick-place (first pass)",
      policyId: selectedPolicyId,
      datasetRepoId: bimanual.repoId,
      datasetRevision: "v2.9",
      requestedGpus: 1,
      state: "DONE",
      queuedReason: null,
      createdIso: "2026-07-19T09:00:00Z",
      startedIso: "2026-07-19T09:01:30Z",
      endedIso: "2026-07-19T13:40:00Z",
      outputDir: "outputs/train/bimanual_pick_place_first",
    },
    {
      jobId: "job_20260718_160000",
      name: "bimanual pick-place (OOM)",
      policyId: selectedPolicyId,
      datasetRepoId: bimanual.repoId,
      datasetRevision: "v2.9",
      requestedGpus: 1,
      state: "FAILED",
      queuedReason: null,
      createdIso: "2026-07-18T16:00:00Z",
      startedIso: "2026-07-18T16:01:10Z",
      endedIso: "2026-07-18T16:04:52Z",
      outputDir: "outputs/train/bimanual_pick_place_oom",
    },
  ];
}

// A completed pos-only (16-dim) run's eight-element lineage snapshot, with the merge
// history the reverse (checkpoint -> episode) query keys on and one recorded PROCEED
// decision (element h). Names length equals stateShape so the record is reproducible.
function lineage(): LineageRecord {
  const names = stateNames(false);
  return {
    dataset: {
      repoId: POS_ONLY_REPO,
      revision: "v3.0",
      infoHash: "sha256:1a2b3c4d5e",
      statsHash: "sha256:9f8e7d6c5b",
    },
    observation: {
      useVelocityAndTorque: false,
      stateShape: names.length,
      actionShape: actionNames().length,
      names,
    },
    mergeHistory: [
      {
        sourceSession: "openarm/bimanual_stack_20260714_090000",
        episodeIndexMap: { "0": 0, "1": 1, "2": 2 },
      },
      {
        sourceSession: "openarm/bimanual_stack_20260715_143000",
        episodeIndexMap: { "0": 3, "1": 4 },
      },
    ],
    trainConfig: {
      steps: 200000,
      batch_size: 8,
      optimizer: { type: "adamw", lr: 1e-4, weight_decay: 1e-6 },
      scheduler: { num_warmup_steps: 2000 },
    },
    pins: {
      codeSha: "2d562db",
      lerobotVersion: snapshotLerobotVersion(),
      containerDigest: "CONTAINER_NOT_USED",
    },
    degenerateDecisions: [
      {
        finding: {
          channelName: `right_joint_7${TORQUE_SUFFIX}`,
          joint: "right_joint_7",
          component: TORQUE_SUFFIX,
          normMode: "MEAN_STD",
          statistic: 3.1e-7,
          threshold: 1e-4,
          amplificationEstimate: 3.2e6,
        },
        choice: "PROCEED",
        rationale: "손목 토크 채널은 이 태스크에 무관 — 증폭을 감수하고 진행",
      },
    ],
  };
}

export function defaultTrainingScreenData(): TrainingScreenData {
  const selectedDataset = bimanualDataset();
  const options = policyOptionsFor(selectedDataset);
  const selectedPolicyId = defaultPolicyId(options);
  return {
    jobs: jobs(selectedPolicyId),
    query: { states: [], nameContains: "", sortBy: "created", descending: true },
    gpuPresent: true,
    gpus: [gpuReading()],
    policies: options,
    selectedPolicyId,
    hyperparams: hyperparams(),
    datasets: [selectedDataset, posOnlyDataset()],
    selectedDatasetRepoId: selectedDataset.repoId,
    vram: vramPreflight(),
    preflight: preflightReport(),
    degenerateFindings: degenerateFindings(),
    degenerateDecisions: [],
    metrics: metricsStream(),
    gpu: gpuReading(),
    checkpoints: checkpoints(),
    lineage: lineage(),
  };
}

export function defaultTrainingSource(): TrainingDataSource {
  return { load: defaultTrainingScreenData };
}
