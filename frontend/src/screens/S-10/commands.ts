// Training-screen command intents (WP-G-S10). The screen is a FACADE: it SENDS
// operator intent to the backend-owned orchestrator (WP-4A-01) and performs no
// validation itself. Three invariants are structural in the op set below:
//
//   - The create-training intent (`create_job`) is the ONLY start op, and the screen
//     emits it exclusively through the start gate (startGate.ts): there is no second
//     start op and no path that reaches the backend while a degenerate finding is
//     undecided (CG-G-S10 ⑤ / FR-TRN-068). The screen's single `emitCreateJob` helper
//     checks `canStartTraining` before it sends — both the start button and a checkpoint
//     resume route through it — so the intent is unreachable while any blocker stands.
//   - A job trains on ONE dataset: `create_job` carries a single `datasetRepoId`, never
//     a list. Multi-dataset training is a MERGE performed in the dataset screen (S-08)
//     first; the training screen names no list (CG-G-S10f).
//   - Degenerate resolution is an intent too (`resolve_degenerate`): the operator's
//     three-way choice per finding, recorded to lineage by the backend (FR-TRN-054 h).

import type { DegenerateChoice, DegenerateFinding, JobQuery } from "./types";

// Apply a filter/sort to the job queue (FR-GUI-120). The backend re-lists; the screen
// owns no sort truth.
export interface QueryJobsCommand {
  op: "query_jobs";
  query: JobQuery;
}

// Cancel a running or queued job (FR-GUI-120). The backend preserves the last
// checkpoint (FR-TRN-032); the screen only asks.
export interface CancelJobCommand {
  op: "cancel_job";
  jobId: string;
}

// Select which policy the form configures. The backend re-emits the capability/block
// verdict for the current observation config; the screen renders it.
export interface SelectPolicyCommand {
  op: "select_policy";
  policyId: string;
}

// Select which dataset (one, by repo_id + revision) the job trains on. There is no
// list form of this op (CG-G-S10f).
export interface SelectDatasetCommand {
  op: "select_dataset";
  datasetRepoId: string;
}

// Override one hyperparameter field. The backend enforces the preset-group rule (change
// one optimizer/scheduler field, re-supply the group).
export interface SetHyperparamCommand {
  op: "set_hyperparam";
  key: string;
  value: string;
}

// Record the forced three-way resolution of one degenerate finding (FR-TRN-068). The
// backend writes it to lineage; the start gate consumes the accumulated decisions.
export interface ResolveDegenerateCommand {
  op: "resolve_degenerate";
  finding: DegenerateFinding;
  choice: DegenerateChoice;
  rationale: string;
}

// Start training on one dataset with one policy and a resolved degenerate set. This is
// the ONLY start op. `resume` names a checkpoint step to continue from, or null for a
// fresh run (FR-TRN-033).
export interface CreateJobCommand {
  op: "create_job";
  name: string;
  policyId: string;
  datasetRepoId: string;
  datasetRevision: string;
  resumeFromStep: number | null;
}

export type TrainingCommand =
  | QueryJobsCommand
  | CancelJobCommand
  | SelectPolicyCommand
  | SelectDatasetCommand
  | SetHyperparamCommand
  | ResolveDegenerateCommand
  | CreateJobCommand;

// The sink a screen publishes intents to. In production this wraps the single WS
// client's control-frame send (WP-G-01), where the server accepts or refuses by
// lease/role — the browser never decides. The default is a no-op so the AI-offline lane
// drives the screen without a backend.
export interface TrainingCommandSink {
  send(command: TrainingCommand): void;
}

export const noopCommandSink: TrainingCommandSink = {
  send: () => {},
};

// Project a command intent onto the frozen CTR-WS command frame body. Kept separate from
// the sink so the wire shape is testable without a socket.
export function commandToWire(command: TrainingCommand): Record<string, unknown> {
  return { type: "command", ...command };
}
