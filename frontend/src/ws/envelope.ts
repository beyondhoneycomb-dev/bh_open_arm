// CTR-WS@v1, mirrored for the browser. This module is the single browser-side
// definition of the frozen single-WebSocket envelope: frame types, their queue
// bindings and priorities, the transported (never redefined) dead-man lease
// fields, the bufferedAmount backpressure rule, and the observer/operator send
// authority. Every value here is a projection of the frozen
// `contracts/ws/envelope.schema.json`; `envelope.contract.test.ts` reads that
// frozen JSON from disk and asserts this mirror equals it, so a CTR-WS bump
// fails the lane (CR-2 staleness) rather than drifting silently. The browser
// TRANSPORTS the lease and does NOT own its semantics (WP-2A-02 canon): the
// proof is structural — a client-authored lease frame carries no expiry field.

// The nine frame types the one WebSocket multiplexes (frozen order).
export const WS_FRAME_TYPES = [
  "telemetry",
  "command",
  "camera",
  "lease_renew",
  "lease_grant",
  "lease_reject",
  "rearm_issue",
  "rearm_confirm",
  "rearm_accept",
] as const;
export type WsFrameType = (typeof WS_FRAME_TYPES)[number];

export const FRAME_DIRECTIONS = ["client_to_server", "server_to_client"] as const;
export type FrameDirection = (typeof FRAME_DIRECTIONS)[number];

export const FRAME_PAYLOADS = ["text", "binary"] as const;
export type FramePayload = (typeof FRAME_PAYLOADS)[number];

// The role a connected client holds. Exactly one operator has command authority;
// every other client is a read-only observer (admin is not a second command source).
export const WS_ROLES = ["observer", "operator", "admin"] as const;
export type WsRole = (typeof WS_ROLES)[number];
export const CONTROL_HOLDER_ROLE: WsRole = "operator";

// Bounded queue classes shared with CTR-PRIM@v1. Priority is served low-first, so
// the lease outranks every other class — the head-of-line mitigation the single
// WS rests on.
export const QUEUE_NAMES = [
  "lease",
  "command",
  "telemetry",
  "camera_preview",
  "capture_match",
] as const;
export type QueueName = (typeof QUEUE_NAMES)[number];

// PriorityClass values (lower is served first). Named so the frame table reads
// priority from its bound queue rather than restating it per frame.
export const PRIORITY_CLASS = {
  lease: 0,
  command: 1,
  telemetry: 2,
  camera: 3,
} as const;
export type PriorityClassName = keyof typeof PRIORITY_CLASS;
export type PriorityValue = (typeof PRIORITY_CLASS)[PriorityClassName];

export const DROP_POLICIES = ["latest_wins", "drop_oldest", "block"] as const;
export type DropPolicy = (typeof DROP_POLICIES)[number];

// What a drop MEANS for a quality report: a lease drop is a DEFECT (the dead-man
// must never lose a renewal), a preview drop is NORMAL (latest-wins by design), a
// counted drop is expected-but-tallied.
export const DROP_CLASSIFICATIONS = ["normal", "defect", "counted"] as const;
export type DropClassification = (typeof DROP_CLASSIFICATIONS)[number];

export interface QueueProfile {
  name: QueueName;
  boundedCapacity: number;
  priority: PriorityValue;
  dropPolicy: DropPolicy;
  dropClassification: DropClassification;
}

// The frozen queue-class defaults. Capacities and drop meanings are CTR-PRIM@v1's.
export const QUEUE_PROFILES: Record<QueueName, QueueProfile> = {
  lease: {
    name: "lease",
    boundedCapacity: 1,
    priority: PRIORITY_CLASS.lease,
    dropPolicy: "latest_wins",
    dropClassification: "defect",
  },
  command: {
    name: "command",
    boundedCapacity: 8,
    priority: PRIORITY_CLASS.command,
    dropPolicy: "drop_oldest",
    dropClassification: "counted",
  },
  telemetry: {
    name: "telemetry",
    boundedCapacity: 16,
    priority: PRIORITY_CLASS.telemetry,
    dropPolicy: "latest_wins",
    dropClassification: "normal",
  },
  camera_preview: {
    name: "camera_preview",
    boundedCapacity: 1,
    priority: PRIORITY_CLASS.camera,
    dropPolicy: "latest_wins",
    dropClassification: "normal",
  },
  capture_match: {
    name: "capture_match",
    boundedCapacity: 4,
    priority: PRIORITY_CLASS.camera,
    dropPolicy: "drop_oldest",
    dropClassification: "counted",
  },
};

// Lease wire field names (CTR-PRIM@v1 pins). The expiry field is on the SERVER
// clock and the issued field on the CLIENT clock; a client-authored frame carries
// the issued field but never the expiry field.
export const LEASE_SESSION_FIELD = "session_id";
export const LEASE_GENERATION_FIELD = "lease_generation";
export const LEASE_GENERATION_CANON_FIELD = "generation";
export const LEASE_SEQUENCE_FIELD = "sequence";
export const LEASE_EXPIRY_FIELD = "expiry_mono_server";
export const LEASE_ISSUED_FIELD = "issued_mono_client";
export const LEASE_REASON_FIELD = "reason";
export const MAX_LEASE_AGE_FIELD = "max_lease_age";
export const EXPIRY_JUDGE_ROLE = "server";
export const AGE_INPUT_ROLE = "client";

export interface FrameSpec {
  frameType: WsFrameType;
  direction: FrameDirection;
  payload: FramePayload;
  queue: QueueName;
  isControlFrame: boolean;
  fields: readonly string[];
}

// One row per frame type. Client lease frames (lease_renew, rearm_confirm) omit
// LEASE_EXPIRY_FIELD by construction — that omission is what makes "the server
// clock is the sole expiry judge" unbreakable from the browser.
export const FRAME_TABLE: Record<WsFrameType, FrameSpec> = {
  telemetry: {
    frameType: "telemetry",
    direction: "server_to_client",
    payload: "text",
    queue: "telemetry",
    isControlFrame: false,
    fields: [],
  },
  command: {
    frameType: "command",
    direction: "client_to_server",
    payload: "text",
    queue: "command",
    isControlFrame: true,
    fields: [],
  },
  camera: {
    frameType: "camera",
    direction: "server_to_client",
    payload: "binary",
    queue: "camera_preview",
    isControlFrame: false,
    fields: [],
  },
  lease_renew: {
    frameType: "lease_renew",
    direction: "client_to_server",
    payload: "text",
    queue: "lease",
    isControlFrame: true,
    fields: [
      LEASE_SESSION_FIELD,
      LEASE_GENERATION_FIELD,
      LEASE_SEQUENCE_FIELD,
      LEASE_ISSUED_FIELD,
    ],
  },
  lease_grant: {
    frameType: "lease_grant",
    direction: "server_to_client",
    payload: "text",
    queue: "lease",
    isControlFrame: false,
    fields: [
      LEASE_SESSION_FIELD,
      LEASE_GENERATION_FIELD,
      LEASE_EXPIRY_FIELD,
      LEASE_SEQUENCE_FIELD,
      LEASE_ISSUED_FIELD,
    ],
  },
  lease_reject: {
    frameType: "lease_reject",
    direction: "server_to_client",
    payload: "text",
    queue: "lease",
    isControlFrame: false,
    fields: [LEASE_SESSION_FIELD, LEASE_GENERATION_FIELD, LEASE_REASON_FIELD],
  },
  rearm_issue: {
    frameType: "rearm_issue",
    direction: "server_to_client",
    payload: "text",
    queue: "lease",
    isControlFrame: false,
    fields: [LEASE_SESSION_FIELD, LEASE_GENERATION_FIELD],
  },
  rearm_confirm: {
    frameType: "rearm_confirm",
    direction: "client_to_server",
    payload: "text",
    queue: "lease",
    isControlFrame: true,
    fields: [LEASE_SESSION_FIELD, LEASE_GENERATION_FIELD],
  },
  rearm_accept: {
    frameType: "rearm_accept",
    direction: "server_to_client",
    payload: "text",
    queue: "lease",
    isControlFrame: false,
    fields: [
      LEASE_SESSION_FIELD,
      LEASE_GENERATION_FIELD,
      LEASE_EXPIRY_FIELD,
      LEASE_SEQUENCE_FIELD,
      LEASE_ISSUED_FIELD,
    ],
  },
};

// The client-authored lease frames. None of them may carry the expiry field.
export const CLIENT_LEASE_FRAMES: readonly WsFrameType[] = ["lease_renew", "rearm_confirm"];

// The three re-arm frames, in the only order a latched lease resumes: server
// issues a generation, operator confirms, server accepts.
export const REARM_HANDSHAKE_FRAMES: readonly WsFrameType[] = [
  "rearm_issue",
  "rearm_confirm",
  "rearm_accept",
];

// The wire reason a renewal was refused or discarded (mirrors RenewalDecision).
export const LEASE_REJECT_REASONS = [
  "rejected_latched",
  "rejected_unarmed",
  "rejected_stale_generation",
  "rejected_unknown_generation",
  "rejected_replay",
  "discarded_aged",
] as const;
export type LeaseRejectReason = (typeof LEASE_REJECT_REASONS)[number];

// Transport: exactly one realtime channel; a parallel realtime stack is forbidden
// (D-2). gRPC is reserved for backend<->remote-inference and is not a browser channel.
export const REALTIME_CHANNEL = "websocket";
export const FORBIDDEN_PARALLEL_STACKS = ["webrtc", "foxglove", "rosbridge", "grpc-web"] as const;

// bufferedAmount backpressure: above the threshold the camera class is shed and
// the lease/command/telemetry classes are protected, so a saturated link never
// delays a dead-man renewal (FR-GUI-042 H2).
export const BUFFERED_AMOUNT_THRESHOLD_BYTES = 1 << 20;
export const BACKPRESSURE_DROP_FRAMES: readonly WsFrameType[] = ["camera"];
export const BACKPRESSURE_PROTECTED_FRAMES: readonly WsFrameType[] = [
  "lease_renew",
  "lease_grant",
  "lease_reject",
  "command",
  "telemetry",
];

// The camera binary frame's `<slot>:<channel>` multiplexing tag (CTR-PRIM@v1 join).
export const WS_TAG_SEPARATOR = ":";

// The image channel kinds a camera frame carries (CTR-PRIM@v1 FrameType): RGB is
// mandatory, depth optional. The same enum tags the WS binary channel and the
// dataset feature key, so a depth stream means the same thing at every surface.
export const CAMERA_CHANNELS = ["rgb", "depth"] as const;
export type CameraChannel = (typeof CAMERA_CHANNELS)[number];

export function isCameraChannel(value: unknown): value is CameraChannel {
  return typeof value === "string" && (CAMERA_CHANNELS as readonly string[]).includes(value);
}

// The camera slot-key grammar (CTR-PRIM@v1 primitive 1): a lowercase snake token,
// safe as a dict key, a column stem, this WS tag, and a dataset feature segment.
export const CAMERA_SLOT_KEY_PATTERN = /^[a-z][a-z0-9_]*$/;

export function isCameraSlotKey(value: unknown): value is string {
  return typeof value === "string" && CAMERA_SLOT_KEY_PATTERN.test(value);
}

// The dataset image feature-key join (CTR-PRIM@v1 primitive 1): a camera slot maps
// to `observation.images.<slot>` (RGB) or `observation.images.<slot>_depth`. The
// meter instruments these keys, so its camera targets derive from the same
// `observation.images.*` subset of `robot.observation_features` (CG-G-01e).
export const IMAGE_FEATURE_PREFIX = "observation.images.";
export const DEPTH_KEY_SUFFIX = "_depth";

export function imageFeatureKey(slot: string, channel: CameraChannel): string {
  const base = `${IMAGE_FEATURE_PREFIX}${slot}`;
  return channel === "depth" ? `${base}${DEPTH_KEY_SUFFIX}` : base;
}

export function isImageFeatureKey(value: string): boolean {
  return value.startsWith(IMAGE_FEATURE_PREFIX);
}

// Build a camera binary frame's `<slot>:<channel>` tag (CTR-PRIM@v1 join).
export function cameraFrameTag(slot: string, channel: CameraChannel): string {
  return `${slot}${WS_TAG_SEPARATOR}${channel}`;
}

// Recover `{slot, channel}` from a `<slot>:<channel>` tag, or null when the tag
// violates the slot grammar or names a channel outside the frozen set.
export function parseCameraFrameTag(tag: string): { slot: string; channel: CameraChannel } | null {
  const separatorIndex = tag.indexOf(WS_TAG_SEPARATOR);
  if (separatorIndex <= 0) {
    return null;
  }
  const slot = tag.slice(0, separatorIndex);
  const channel = tag.slice(separatorIndex + WS_TAG_SEPARATOR.length);
  if (!isCameraSlotKey(slot) || !isCameraChannel(channel)) {
    return null;
  }
  return { slot, channel };
}

// Transport security the control channel is served under (FR-GUI-092 H3).
export const WS_SECURE_SCHEME = "wss";
export const WS_PLAINTEXT_SCHEME = "ws";

// A public health payload must never leak who holds control or which profile is live.
export const PUBLIC_HEALTH_FORBIDDEN_FIELDS = ["control_holder", "active_profile"] as const;

export function frameSpec(frameType: WsFrameType): FrameSpec {
  return FRAME_TABLE[frameType];
}

export function framePriority(frameType: WsFrameType): PriorityValue {
  return QUEUE_PROFILES[FRAME_TABLE[frameType].queue].priority;
}

export function isControlFrame(frameType: WsFrameType): boolean {
  return FRAME_TABLE[frameType].isControlFrame;
}

export function isWsFrameType(value: unknown): value is WsFrameType {
  return typeof value === "string" && (WS_FRAME_TYPES as readonly string[]).includes(value);
}

// Whether every client-authored lease frame omits the expiry field (structural
// proof that the browser cannot author an expiry).
export function clientLeaseFramesOmitExpiry(): boolean {
  return CLIENT_LEASE_FRAMES.every(
    (frame) => !FRAME_TABLE[frame].fields.includes(LEASE_EXPIRY_FIELD),
  );
}

// Whether a frame is shed at a given send-buffer level: only a camera frame, and
// only once bufferedAmount is over threshold. This is the frozen predicate the
// backend uses, applied on the browser to its own socket-saturation signal.
export function shouldDropUnderBackpressure(
  frameType: WsFrameType,
  bufferedAmount: number,
): boolean {
  return (
    BACKPRESSURE_DROP_FRAMES.includes(frameType) &&
    bufferedAmount > BUFFERED_AMOUNT_THRESHOLD_BYTES
  );
}

export class WsAuthorityError extends Error {
  readonly role: WsRole;
  readonly frameType: WsFrameType;

  constructor(role: WsRole, frameType: WsFrameType) {
    super(
      `role '${role}' may not send control frame '${frameType}'; command authority ` +
        `is held only by '${CONTROL_HOLDER_ROLE}'`,
    );
    this.name = "WsAuthorityError";
    this.role = role;
    this.frameType = frameType;
  }
}

// The frozen server-side rule (authorize_send): an observer sending any control
// frame is refused. Mirrored here so the browser applies the same predicate the
// server enforces — client-side hiding alone is insufficient (CG-G-01g).
export function authorizeSend(role: WsRole, frameType: WsFrameType): void {
  if (isControlFrame(frameType) && role !== CONTROL_HOLDER_ROLE) {
    throw new WsAuthorityError(role, frameType);
  }
}

// Whether a health payload would leak a forbidden field (control holder / profile).
export function healthLeaks(payload: Record<string, unknown>): string[] {
  return PUBLIC_HEALTH_FORBIDDEN_FIELDS.filter((field) => field in payload);
}
