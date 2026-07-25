// Backend state contracts the dashboard (WP-G-S01, route /) mirrors as TS RENDER
// SHAPES. S-01 OWNS NOTHING: it aggregates values every other domain already
// computed and renders them, computing no metric and deciding no threshold of its
// own (CG-G-S01a / CG-5-02). A second aggregator that recomputes would be a second
// truth. Every field below is produced by a backend WP and arrives over the
// CTR-WS envelope; this file only names the shapes so the screen can render them
// and never re-source, re-compute, or re-decide any of them (02d §2.2, 02c §4.2).
//
// The load-bearing invariants are structural in the shapes here:
//   - a subsystem's `status` is one of the four diagnostic_msgs/DiagnosticStatus
//     states verbatim (14 §4.3), or `null` when its source has not landed — which
//     the screen renders as UNAVAILABLE, never as OK (CG-G-S01e). Filling a gap
//     with a green is the get_observation()-fills-missing-with-0 bug.
//   - the cycle-time p95 is the PG-RT-001b artifact's, carried with that
//     provenance; it is never self-measured and never the provisional PG-RT-001a
//     (CG-G-S01d / CG-5-02d). On this offline box the artifact has not landed, so
//     the shape is the unavailable variant.
//   - the WARN cause split is the backend's four named parts or an explicit
//     "unimplemented" — never a silent total (CG-5-02e).
//   - the public (unauthenticated) health projection omits the control-holder and
//     active-profile id (health.ts, CG-5-02c / FR-OPS-027).

// The four subsystem states, diagnostic_msgs/DiagnosticStatus semantics borrowed
// verbatim (14 §4.3 / §4.6 — ROS 2 is not in our runtime, only the four names).
export const DIAGNOSTIC_STATES = ["OK", "WARN", "ERROR", "STALE"] as const;
export type DiagnosticState = (typeof DIAGNOSTIC_STATES)[number];

// The render-state a tile shows: one of the four diagnostic states, or the
// UNAVAILABLE sentinel a not-landed source resolves to. UNAVAILABLE is NOT a
// fifth diagnostic state (14 §4.3 has four); it is "there is no value to show",
// distinct from STALE ("the source is there but its heartbeat/poll failed").
export const UNAVAILABLE = "UNAVAILABLE" as const;
export type SubsystemRenderState = DiagnosticState | typeof UNAVAILABLE;

// The nine subsystem rows of 14 §4.3 the dashboard renders (02c §4.2 interface
// contract: "the nine rows ... we do not invent a row"). The canon is exactly
// these nine ids; the screen renders whatever the backend supplies keyed by them
// and adds none. The four §4.3 rows the WP-5-02 contract does not name (policy
// server, disk-as-subsystem, control-lock) are intentionally out of this set —
// disk is an FR-GUI-100 metric tile, not a §4.3 subsystem row here.
export const CANONICAL_SUBSYSTEM_IDS = [
  "can",
  "motors",
  "control_loop",
  "cameras",
  "vr_link",
  "ik_solver",
  "gui_backend",
  "zero_integrity",
  "dataset_contract",
] as const;
export type SubsystemId = (typeof CANONICAL_SUBSYSTEM_IDS)[number];

// One §4.3 subsystem row as the backend reports it. `status` is null when the
// producing backend has not landed (its source is absent) — the screen resolves
// that to UNAVAILABLE and never to OK (CG-G-S01e). `critical` is the backend's
// CRITICAL marker (e.g. GUI-backend STALE = process death = fall risk, 14 §4.3 /
// §4.4 F17 OA-SYS-004) that lifts the row into the CRITICAL-only area; the screen
// renders the marker and never decides criticality itself (CG-G-S01a).
export interface SubsystemStatus {
  id: SubsystemId;
  label: string;
  status: DiagnosticState | null;
  detail: string;
  critical: boolean;
}

// Connection + mode (FR-GUI-100). `controlHolder` and `activeProfileId` are the
// AUTHENTICATED operator-console fields; the public health projection strips them
// (health.ts, CG-5-02c / FR-OPS-027). `mode` is the backend's mode token — the
// mode canon is the mode foundation's, not the dashboard's, so it stays a string.
export interface ConnectionMode {
  connected: boolean;
  mode: string;
  sessionId: string;
  controlHolder: string | null;
  activeProfileId: string | null;
}

// Per-interface CAN status (FR-GUI-061). SocketCAN gives no exclusive bind (F-1),
// so ownership is "do WE hold the flock lock, and is there an intruder", not "who
// owns it". `intruderPresent` and `intruderPids` are the backend's finding
// (WP-0B-03/04); the screen renders them and computes no presence itself
// (CG-5-02g).
export interface CanInterfaceStatus {
  iface: string;
  lockHeld: boolean;
  boundSocketCount: number;
  intruderPresent: boolean;
  intruderPids: readonly number[];
  state: DiagnosticState | null;
}

// The coupled data-flag pair (FR-GUI-072 / FR-GUI-073), always shown (CG-5-02f).
// `useVelocityAndTorque` is the follower+leader coupled single switch; the
// dashboard reflects it, it does not toggle it here. `pushToHub` true is a risk
// surfaced with its own marker.
export interface DataFlags {
  useVelocityAndTorque: boolean;
  pushToHub: boolean;
}

// One active camera stream's stats (FR-GUI-100, FR-CAM-001). The dashboard's tile
// count is the LENGTH of the active-stream array, never a constant (CG-G-S01c /
// CG-5-02b): add or drop a stream and the tile set follows. `uiLabel` and
// `datasetKey` differ (bi_openarm_follower auto-prefixes per arm) and both are
// carried. `state` is the backend's per-stream diagnostic; the numbers are shown
// verbatim, never thresholded here.
export interface CameraStreamStat {
  slot: string;
  uiLabel: string;
  datasetKey: string;
  fps: number;
  jitterMs: number;
  state: DiagnosticState | null;
}

// Disk headroom (FR-GUI-100). Free space and the PROJECTED exhaustion time both
// arrive pre-formatted from the backend (the projection is a backend estimate,
// FR-REC-020-class); `exhaustionDisplay` null means the backend could not
// project one — the screen shows a "not projectable" label, never a fabricated date.
export interface DiskStatus {
  freeBytes: number;
  freeDisplay: string;
  exhaustionDisplay: string | null;
  state: DiagnosticState | null;
}

// GPU / VRAM (FR-GUI-100). `vramDisplay` is the backend-formatted "used / total"
// string so the screen shows no ratio arithmetic. `present` false (no GPU on this
// host) resolves the tile to UNAVAILABLE, never OK.
export interface GpuStatus {
  present: boolean;
  name: string;
  vramDisplay: string;
  utilizationDisplay: string;
  temperatureDisplay: string;
  state: DiagnosticState | null;
}

// The four cause channels a control-loop WARN decomposes into (NFR-GUI-011). Each
// is the backend's measured contribution; the screen renders all four and never
// shows a bare total that hides which channel is the cost (CG-5-02e).
export interface CycleCauseBreakdown {
  kind: "cause-breakdown";
  canMs: number;
  cameraGrabEncodeMs: number;
  ikMs: number;
  wsSerializationMs: number;
  consecutiveCycles: number;
}

// The explicit alternative to a cause split: the backend states the decomposition
// is not implemented (the four instrumentation hooks would add loop jitter, a
// trade decided by the PG-RT-001b result — 02c §4.2 negative branch). Rendering
// this is a PASS; a silent total is the FAIL.
export interface CycleCauseUnimplemented {
  kind: "unimplemented";
  note: string;
}

export type CycleWarnDetail = CycleCauseBreakdown | CycleCauseUnimplemented;

// The loop cycle-time item (FR-GUI-100 / NFR-GUI-011). Its source is the
// PG-RT-001b artifact (Wave 3C real-load final canon, NFR-PRF-054) and nothing
// else: never self-measured, never the provisional PG-RT-001a. When the artifact
// has not landed — as on this offline box, hardware-deferred — the shape is the
// unavailable variant and the tile reads UNAVAILABLE (CG-G-S01d/e). When present,
// a WARN carries either the four-way cause split or the explicit-unimplemented
// note (CG-5-02e). `warn` null means the loop is meeting its target (no WARN).
export const CYCLE_TIME_SOURCE = "PG-RT-001b" as const;

export type CycleTime =
  | { available: false; source: typeof CYCLE_TIME_SOURCE; reason: string }
  | {
      available: true;
      source: typeof CYCLE_TIME_SOURCE;
      p50Ms: number;
      p95Ms: number;
      p99Ms: number;
      targetDisplay: string;
      warn: CycleWarnDetail | null;
    };

// One recent data-collection / rollout session summary (FR-GUI-100). All fields
// are backend-formatted; the screen lists them and ranks nothing.
export interface RecentSession {
  id: string;
  name: string;
  startedDisplay: string;
  episodeCount: number;
  outcome: string;
}

// The unacknowledged-warning tally (FR-GUI-100). The count and the highest
// severity among them are the notification center's (WP-G-03); the dashboard
// mirrors the tally and decides no severity itself.
export interface UnackedWarnings {
  count: number;
  highestSeverity: DiagnosticState | null;
}

// The whole dashboard snapshot the backend surfaces over the single WS. It is a
// snapshot; in production a live source pushes fresh snapshots and the AI-offline
// lane injects a deterministic fixture. Every member is a mirror of a value some
// other domain already owns — the dashboard aggregates, it originates nothing.
export interface DashboardData {
  connection: ConnectionMode;
  can: readonly CanInterfaceStatus[];
  flags: DataFlags;
  cameras: readonly CameraStreamStat[];
  disk: DiskStatus;
  gpu: GpuStatus;
  cycleTime: CycleTime;
  subsystems: readonly SubsystemStatus[];
  sessions: readonly RecentSession[];
  unacked: UnackedWarnings;
  activeErrorCodes: readonly string[];
}

// The data seam. The default implementation returns an offline fixture; a test
// injects a deterministic snapshot. No implementation here reaches a real backend
// or opens a socket — the single WebSocket is the foundation's (WP-G-01), and the
// dashboard never constructs one (invariant I-2). There is no reconnect path.
export interface DashboardSource {
  load(): DashboardData;
}
