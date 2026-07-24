// Training screen (WP-G-S10, route /training). A FACADE over the TRN domain (10): it
// renders the Wave 4A/4B backend's training surface — the job queue, the source-derived
// policy capabilities, the dataset preflight, the degenerate findings, the local metrics,
// the checkpoints and the lineage snapshot — and emits operator intent. It owns no domain
// truth: the policy list is runtime-derived data, the preflight/degenerate verdicts are
// the backend's, and the screen recomputes none of them.
//
// The one rule this screen enforces itself is the START GATE (startGate.ts): there is a
// SINGLE start control, it is disabled whenever the gate is not clear, and the create_job
// intent is emitted only past `canStartTraining`. So there is no UI path to start training
// while a degenerate channel is undecided (CG-G-S10 ⑤ / FR-TRN-068), the preflight has not
// PASSED, the policy is blocked, or VRAM does not fit. Like the sibling screens it renders
// from a `source` prop with an offline default fixture and a no-op `commandSink`, opens no
// socket and offers no reconnect (invariant I-2).
//
// The gates this screen keeps, and where each is kept:
//   - CG-G-S10a policy list runtime-derived, 0 hardcoded names → policyRegistry / snapshot
//   - CG-G-S10b chart keys ⊆ MetricsTracker's 7               → metrics / LossCurveView
//   - CG-G-S10c loss curve renders with W&B disabled          → LossCurveView
//   - CG-G-S10d checkpoint default not val-loss-min + warning  → checkpointSelection / list
//   - CG-G-S10e VRAM exceeded → start disabled + source        → startGate / DatasetFormView
//   - CG-G-S10f no multi-dataset list UI + merge guidance      → DatasetFormView / commands
//   - CG-G-S10g vqbet unavailable shown + blocked              → policyRegistry / PolicyForm
//   - CG-G-S10h GPU-absent QUEUED distinct                     → JobQueueView
//   - CG-G-S10 ⑤ no start without the degenerate 3-choice      → startGate / this screen

import { useMemo, useState } from "react";

import "./training.css";
import { CheckpointListView } from "./CheckpointListView";
import { DatasetFormView } from "./DatasetFormView";
import { DegenerateReviewView } from "./DegenerateReviewView";
import { JobQueueView } from "./JobQueueView";
import { LineageView } from "./LineageView";
import { LossCurveView } from "./LossCurveView";
import { PolicyFormView } from "./PolicyFormView";
import { PreflightReportView } from "./PreflightReportView";
import { snapshotLerobotVersion } from "./policyRegistry";
import { canStartTraining, startBlockReasons } from "./startGate";
import { defaultTrainingSource } from "./trainingSource";
import { noopCommandSink, type TrainingCommandSink } from "./commands";
import type {
  DegenerateChoice,
  DegenerateDecision,
  DegenerateFinding,
  HyperparamField,
  JobQuery,
  TrainingDataSource,
} from "./types";

export interface TrainingScreenProps {
  source?: TrainingDataSource;
  commandSink?: TrainingCommandSink;
}

const DEFAULT_SOURCE: TrainingDataSource = defaultTrainingSource();

export default function TrainingScreen({
  source,
  commandSink = noopCommandSink,
}: TrainingScreenProps) {
  const resolved = source ?? DEFAULT_SOURCE;
  const data = useMemo(() => resolved.load(), [resolved]);

  const [policyId, setPolicyId] = useState(data.selectedPolicyId);
  const [datasetRepoId, setDatasetRepoId] = useState(data.selectedDatasetRepoId);
  const [query, setQuery] = useState<JobQuery>(data.query);
  const [hyperparams, setHyperparams] = useState<readonly HyperparamField[]>(data.hyperparams);
  const [decisions, setDecisions] = useState<readonly DegenerateDecision[]>(data.degenerateDecisions);
  const [jobName, setJobName] = useState("");

  const selectedPolicy = data.policies.find((option) => option.capability.id === policyId) ?? null;
  const selectedDataset = data.datasets.find((dataset) => dataset.repoId === datasetRepoId) ?? null;

  const gateInput = {
    policy: selectedPolicy,
    preflight: data.preflight,
    findings: data.degenerateFindings,
    decisions,
    vram: data.vram,
  };
  const blockReasons = startBlockReasons(gateInput);
  const canStart = canStartTraining(gateInput);

  function changeQuery(next: JobQuery): void {
    setQuery(next);
    commandSink.send({ op: "query_jobs", query: next });
  }

  function cancelJob(jobId: string): void {
    commandSink.send({ op: "cancel_job", jobId });
  }

  function selectPolicy(nextPolicyId: string): void {
    setPolicyId(nextPolicyId);
    commandSink.send({ op: "select_policy", policyId: nextPolicyId });
  }

  function selectDataset(repoId: string): void {
    setDatasetRepoId(repoId);
    commandSink.send({ op: "select_dataset", datasetRepoId: repoId });
  }

  function setHyperparam(key: string, value: string): void {
    setHyperparams((prev) =>
      prev.map((field) => (field.key === key ? { ...field, value } : field)),
    );
    commandSink.send({ op: "set_hyperparam", key, value });
  }

  function resolveDegenerate(
    finding: DegenerateFinding,
    choice: DegenerateChoice,
    rationale: string,
  ): void {
    setDecisions((prev) => {
      const rest = prev.filter(
        (decision) =>
          !(
            decision.finding.channelName === finding.channelName &&
            decision.finding.normMode === finding.normMode
          ),
      );
      return [...rest, { finding, choice, rationale }];
    });
    commandSink.send({ op: "resolve_degenerate", finding, choice, rationale });
  }

  // The SINGLE gated create_job emitter — the ONLY site that sends the training intent.
  // Both the start button and a checkpoint resume route through here, so no path can emit
  // it while any blocker stands (CG-G-S10 ⑤ / FR-TRN-068): a resume still starts a run, so
  // it obeys the same gate as a fresh start. Keeping one emit site is what makes the static
  // no-bypass check (staticChecks) able to prove there is no second, ungated path.
  function emitCreateJob(resumeFromStep: number | null): void {
    if (!canStart || selectedDataset === null) {
      return;
    }
    const suffix = resumeFromStep === null ? "" : ` resume@${resumeFromStep}`;
    commandSink.send({
      op: "create_job",
      name: jobName || `${selectedDataset.repoId}${suffix}`,
      policyId,
      datasetRepoId,
      datasetRevision: selectedDataset.revision,
      resumeFromStep,
    });
  }

  function startTraining(): void {
    emitCreateJob(null);
  }

  function resumeCheckpoint(step: number): void {
    emitCreateJob(step);
  }

  return (
    <div className="oa-trn" data-screen="S-10">
      <header className="oa-trn__head">
        <p className="oa-trn__id">/training</p>
        <h1 className="oa-trn__title">학습</h1>
        {!data.gpuPresent && (
          <p className="oa-trn__badge oa-trn__badge--blocked" data-testid="no-gpu-banner">
            GPU 미탑재 — 큐 작업은 GPU 확보 시까지 대기
          </p>
        )}
      </header>

      <JobQueueView jobs={data.jobs} query={query} onQuery={changeQuery} onCancel={cancelJob} />

      <div className="oa-trn__form-grid">
        <PolicyFormView
          options={data.policies}
          selectedPolicyId={policyId}
          lerobotVersion={snapshotLerobotVersion()}
          hyperparams={hyperparams}
          onSelectPolicy={selectPolicy}
          onSetHyperparam={setHyperparam}
        />
        <DatasetFormView
          datasets={data.datasets}
          selectedRepoId={datasetRepoId}
          vram={data.vram}
          onSelectDataset={selectDataset}
        />
      </div>

      <PreflightReportView report={data.preflight} />

      <DegenerateReviewView
        findings={data.degenerateFindings}
        decisions={decisions}
        onResolve={resolveDegenerate}
      />

      <section className="oa-trn__panel oa-trn__start" aria-labelledby="oa-trn-start-title">
        <h2 id="oa-trn-start-title" className="oa-trn__section-title">
          학습 시작
        </h2>
        <label className="oa-trn__field">
          <span>잡 이름</span>
          <input
            type="text"
            value={jobName}
            data-testid="job-name"
            onChange={(event) => setJobName(event.target.value)}
          />
        </label>

        {blockReasons.length > 0 && (
          <ul className="oa-trn__block-reasons" data-testid="start-block-reasons">
            {blockReasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        )}

        <button
          type="button"
          className="oa-trn__primary"
          data-testid="start-training"
          disabled={!canStart}
          onClick={startTraining}
        >
          학습 시작
        </button>
      </section>

      <LossCurveView metrics={data.metrics} />

      <CheckpointListView
        checkpoints={data.checkpoints}
        onResume={resumeCheckpoint}
        canResume={canStart}
      />

      <LineageView lineage={data.lineage} />
    </div>
  );
}
