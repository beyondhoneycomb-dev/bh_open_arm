// Backend wire shapes the data-collection screen (WP-G-S07, /collect) renders.
// S-07 is a FACADE over the REC domain (07): the stamped repo_id, the drop
// counts, the storage prediction, the resumable sessions and the WP-3C gate
// verdicts all originate in the committed 3B/3C backend (WP-3B-11/12, WP-3C-02/
// 06/07) and arrive here as WS/contract data. This file names those shapes so the
// screen can render them and never re-source, re-compute, or re-decide any of them
// (02d §2.2 — the collection canon is domain 07). The two flag inputs the start
// gate reuses (push_to_hub, preflight) come straight from the WP-G-03 global surface.

import type { DropClassification } from "../../ws/envelope";
import type { PreflightItem, PushToHubState } from "../../global";

// The dataset's identity as the backend produced it. `stampedRepoId` is the
// output of the backend `stamp_repo_id()` (WP-3B-11 acceptance ⑤); it is the name
// display, storage and Resume all key on. `requestedRepoId` is the operator's raw
// input, carried only so the screen can show "you asked for X, it was stamped to
// Y" — it must never be shown AS the dataset name (CG-G-S07b).
export interface DatasetIdentity {
  requestedRepoId: string;
  stampedRepoId: string;
}

// The LeRobot `single_task` string attached to every recorded frame (TASK_KEY).
// Owned by the backend recorder config; the screen renders it and sends an intent
// to change it.
export interface TaskPrompt {
  text: string;
}

// The backend-owned episode-control flags (RecordEvents.as_dict()), mirrored for
// display only. These are set by S-07's episode-control intents, never by a
// captured keypress (WP-3B-11 acceptance ②). Rendering them makes visible which
// control the running record_loop is about to act on.
export interface EpisodeControlState {
  exitEarly: boolean;
  rerecordEpisode: boolean;
  stopRecording: boolean;
}

// One WS-transmit channel's drop exposure: frames the single WebSocket shed on
// send (queue eviction / backpressure), classified by CTR-WS@v1. This is the
// preview/telemetry transmit path — kept STRICTLY separate from capture/encode
// drops (CG-G-S07c), because merging them hides whether a lost frame was the
// browser link or the camera pipeline.
export interface WsTransmitDrop {
  channel: string;
  dropCount: number;
  classification: DropClassification;
}

// Per-slot camera capture/encode drop exposure, from the backend quality report
// (CameraDropStats, WP-3B-12). A device frame-counter gap or a missing sidecar row
// is a capture-side loss — a different fault from a WS transmit drop.
export interface CameraCaptureDrop {
  slot: string;
  missingRows: number;
  frameNumberGaps: number;
}

// CAN-drop exposure over the observation stream (CanDropStats, WP-3B-12): the
// recorder's authoritative flag count plus the heuristic stale-reuse count. Part
// of the capture side, never folded into the WS transmit total.
export interface CanCaptureDrop {
  flaggedFrames: number;
  suspectedStaleFrames: number;
}

// The drop report for the current/last episode, split at the source into the two
// causes the operator must be able to tell apart (CG-G-S07c). `frameCount` is the
// episode length both rates are measured against.
export interface DropReport {
  frameCount: number;
  wsTransmit: readonly WsTransmitDrop[];
  camera: readonly CameraCaptureDrop[];
  can: CanCaptureDrop;
}

// The backend disk watch's prediction for the active recording (WP-3B-12 diskwatch
// / WP-3C-02). `bytesPerHour` is the backend's fill-rate estimate and
// `headroomHours` its free/rate quotient; the screen renders both and blocks the
// start below one hour of headroom (CG-G-S07g) using the shared global constant —
// it computes neither figure itself.
export interface StoragePrediction {
  freeBytes: number;
  totalBytes: number;
  bytesPerHour: number;
  headroomHours: number;
}

// A session the backend detected as interrupted (crash / disk-low), offered for
// Resume (WP-3C-07). It is keyed by the stamped repo_id, and Resume restores THAT
// id unchanged (CG-G-S07e) — re-stamping would fork the name and lose the data.
export interface ResumableSession {
  stampedRepoId: string;
  recordedEpisodes: number;
  reason: string;
  requiresUserJudgment: boolean;
}

// The lifecycle state of a WP-3C hardware gate as it reaches the screen. The gates
// are not built yet (WP-3C-02/06/07 are HW), so their verdict currently arrives as
// `pending`/`unavailable`; the screen renders that honestly and never fabricates a
// verdict or blocks on a gate that has not landed.
export const GATE_STATES = [
  "pending",
  "unavailable",
  "degraded_accepted",
  "pass",
  "fail",
] as const;
export type GateState = (typeof GATE_STATES)[number];

// One WP-3C gate row S-07 renders. The backend owns the verdict; the screen owns
// only how a missing/degraded verdict is shown.
export interface GateStatus {
  id: string;
  label: string;
  state: GateState;
  detail: string | null;
}

// The whole S-07 payload the backend surfaces (over the single WS + REST). It is a
// snapshot; in production a live source pushes fresh snapshots as the record_loop
// advances, and the AI-offline lane injects deterministic fixtures.
export interface CollectData {
  sessionActive: boolean;
  events: EpisodeControlState;
  dataset: DatasetIdentity;
  taskPrompt: TaskPrompt;
  recordedEpisodeCount: number;
  dropReport: DropReport;
  storage: StoragePrediction;
  preflight: readonly PreflightItem[];
  pushToHub: PushToHubState;
  resumable: readonly ResumableSession[];
  gates: readonly GateStatus[];
}

// The data seam. The default implementation returns an offline fixture; a test
// injects a deterministic snapshot. No implementation here reaches a real backend
// or opens a socket — the single WebSocket is the foundation's (WP-G-01), and the
// screen never constructs one (invariant I-2).
export interface CollectDataSource {
  load(): CollectData;
}
