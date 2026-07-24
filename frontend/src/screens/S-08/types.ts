// Backend wire shapes the dataset screen (WP-G-S08, /datasets) renders. S-08 is a
// FACADE over the DAT domain (08): the dataset inventory, the per-episode signals,
// the capture_ts jitter sidecar, the success/fail label sidecar, the integrity
// verification report and the copy-on-write edit preview all originate in the
// committed Wave 3D backend (WP-3D-01..05, WP-3D-07) and arrive here as CTR-WS
// envelope data or file direct-read. This file names those shapes so the screen can
// render them and never re-source, re-compute, or re-decide any of them (02d §2.2 —
// the dataset canon is domain 08). Four invariants are structural and live in the
// shapes below:
//   - observation.state is ONE vector; .pos/.vel/.torque are pulled by the info.json
//     `names` index, so `state` is a (frames × dim) matrix keyed by `stateNames`,
//     never a fixed slot (CG-G-S08a).
//   - `observation.effort` does not exist — no field here names it (CG-G-S08b).
//   - `timestamp` is the synthetic grid frame_index/fps, carried with
//     `timestampIsWallClock: false`; real capture jitter is the separate
//     `captureJitter` sidecar (CG-G-S08c).
//   - the success/fail label is a sidecar attribute, not a parquet column
//     (CG-G-S08d), and every edit is copy-on-write to a new repo_id (CG-G-S08f).

// One dataset's identity in the browse list, projected from meta/info.json plus the
// lineage store (WP-3D-04). `stampedRepoId` is the backend `stamp_repo_id()` output
// the whole screen keys on; `contentHash` is the copy-on-write-stable identity, so
// an edited copy is a distinct row. `useVelocityAndTorque` fixes whether the state
// vector is the 24-dim (pos+vel+torque) or 8-dim (pos-only) shape — the exact toggle
// a fixed channel index would silently scramble (CG-G-S08a).
export interface DatasetSummary {
  stampedRepoId: string;
  contentHash: string;
  revision: string;
  totalEpisodes: number;
  totalFrames: number;
  stateDim: number;
  useVelocityAndTorque: boolean;
  fps: number;
}

// The synthetic playback grid one episode is plotted against, mirrored from the
// backend `TimeAxis` (WP-3D-01 signals). `timestamps[i] = frameIndices[i] / fps` is
// a grid COORDINATE, not a capture instant, so `isWallClock` is always false and the
// UI states as much rather than letting jitter be read off this axis (CG-G-S08c).
export interface TimeAxis {
  fps: number;
  frameIndices: readonly number[];
  timestamps: readonly number[];
  isWallClock: false;
  domainNote: string;
}

// One episode's state/action series on the shared grid axis, mirrored from the
// backend `EpisodeSignals`. `state` is (frames × state_dim) and `action` is
// (frames × action_dim); the channel names carry the dataset order, and a channel is
// resolved by `stateNames.indexOf(name)` — never a compiled-in column (CG-G-S08a).
export interface EpisodeSignals {
  episodeIndex: number;
  timeAxis: TimeAxis;
  stateNames: readonly string[];
  actionNames: readonly string[];
  state: readonly (readonly number[])[];
  action: readonly (readonly number[])[];
}

// The capture-time sidecar for one camera slot (backend camera reverify
// `capture_ts.json` — `{slot: [capture_ts_ns, ...]}`). This is the ONLY honest
// source of real capture jitter; the synthetic `timestamp` grid would show jitter as
// a flat zero (CG-G-S08c). Values are nanoseconds, one per captured frame.
export interface CaptureTsSidecar {
  slot: string;
  captureTsNs: readonly number[];
}

// One judgment of an episode, mirrored from the backend `Judgment` (WP-3B-12 label
// sidecar). `provenance` is `auto` (offline suggestion) or `manual` (human verdict).
export interface Judgment {
  verdict: "success" | "fail";
  provenance: "auto" | "manual";
}

// The lifecycle state of an episode's label sidecar (backend `EpisodeStatus`).
export const EPISODE_LABEL_STATES = ["judged", "pending_judgment", "aborted"] as const;
export type EpisodeLabelStatus = (typeof EPISODE_LABEL_STATES)[number];

// The success/fail label as it reaches the screen, mirrored from the backend
// `EpisodeLabel` sidecar (WP-3B-12). The label is a SIDECAR attribute, not a parquet
// column (CG-G-S08d); both `auto` and `manual` are kept so a human override never
// erases the suggestion and a mismatch stays queryable. The screen renders these and
// never fabricates a verdict — an episode with neither judgment reads as unlabelled.
export interface EpisodeLabel {
  episodeIndex: number;
  status: EpisodeLabelStatus;
  auto: Judgment | null;
  manual: Judgment | null;
  abortReason: string | null;
  autoSaved: boolean;
}

// One episode row in the selected dataset, joining the packed-parquet episode
// metadata (length, tasks) with its label sidecar. `label` may be null for an
// episode the backend has not judged; the screen shows that honestly.
export interface EpisodeSummary {
  episodeIndex: number;
  length: number;
  tasks: readonly string[];
  label: EpisodeLabel | null;
}

// One configured camera stream from info.json (backend `CameraStream`, WP-3D-01
// channels). The count and RGB/depth split are read from the feature set, never a
// fixed slot table. `imageKey` is the full `observation.images.<slot>[_depth]` key
// the camera-synced playback pane keys each tile on.
export interface CameraStream {
  imageKey: string;
  slot: string;
  isDepth: boolean;
  shape: readonly (number | string)[];
}

// One integrity check outcome, mirrored from the backend `CheckResult` (WP-3D-05).
// `status` is the binary pass/fail the verifier produces — there is no warning level.
export interface CheckResult {
  name: string;
  status: "pass" | "fail";
  detail: string;
}

// The full verification report for one dataset, mirrored from the backend
// `IntegrityReport` (WP-3D-05). The verdict (`READY`/`INVALID`), the `ready` flag and
// the `missingChecks` list are the BACKEND's — the screen renders them and never
// recomputes readiness, so a check the verifier skipped cannot be certified away by
// the UI. A missing check counts against readiness exactly as loudly as a failed one.
export interface VerificationReport {
  root: string;
  results: readonly CheckResult[];
  ready: boolean;
  verdict: "READY" | "INVALID";
  missingChecks: readonly string[];
  elapsedSeconds: number;
  datasetBytes: number;
}

// How a copy-on-write edit interacts with the backend engine, mirrored from the
// backend `OperationPolicy` (WP-3D-02). `inPlace` names an upstream operation that
// mutates its input directory (modify_tasks / recompute_stats / reencode) — the
// engine copies FIRST, so even an in-place upstream op is CoW at this boundary
// (CG-G-S08f). The screen renders the policy to make the copy-first guarantee visible.
export interface EditOperationPolicy {
  renumbers: boolean;
  inPlace: boolean;
  multiOutput: boolean;
  crossDataset: boolean;
}

// A previewed copy-on-write edit the backend prepared (WP-3D-02 preview). The edit
// always writes to a NEW `outputRepoId` the backend stamped — the original is
// immutable (CG-G-S08f). The screen renders this preview and emits the intent to run
// it; it never generates the output id itself and never offers an in-place path.
export interface EditPreview {
  operation: string;
  policy: EditOperationPolicy;
  sourceRepoId: string;
  outputRepoId: string;
  summary: string;
}

// The whole S-08 payload the backend surfaces (over the single WS + file direct-
// read). It is a snapshot; in production a live source pushes fresh snapshots and the
// AI-offline lane injects a deterministic fixture. `selectedRepoId` names which of
// `datasets` the episode/signals/report views are showing.
export interface DatasetScreenData {
  datasets: readonly DatasetSummary[];
  selectedRepoId: string;
  episodes: readonly EpisodeSummary[];
  selectedEpisodeIndex: number;
  signals: EpisodeSignals;
  cameraStreams: readonly CameraStream[];
  captureJitter: readonly CaptureTsSidecar[];
  verification: VerificationReport;
  editPreview: EditPreview | null;
}

// The data seam. The default implementation returns an offline fixture; a test
// injects a deterministic snapshot. No implementation here reaches a real backend or
// opens a socket — the single WebSocket is the foundation's (WP-G-01), and the screen
// never constructs one (invariant I-2).
export interface DatasetDataSource {
  load(): DatasetScreenData;
}
