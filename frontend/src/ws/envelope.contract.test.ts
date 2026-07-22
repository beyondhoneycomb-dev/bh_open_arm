// The consume-the-frozen-contract proof. This reads the frozen
// `contracts/ws/envelope.schema.json` (CTR-WS@v1) and `contracts/prim/schema.json`
// (CTR-PRIM@v1) from disk and asserts the browser mirror in envelope.ts equals
// them field for field. A CTR-WS or CTR-PRIM bump changes those bytes and fails
// this test — the browser cannot silently drift from the frozen envelope (CR-2).

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  AGE_INPUT_ROLE,
  BACKPRESSURE_DROP_FRAMES,
  BACKPRESSURE_PROTECTED_FRAMES,
  BUFFERED_AMOUNT_THRESHOLD_BYTES,
  clientLeaseFramesOmitExpiry,
  CONTROL_HOLDER_ROLE,
  EXPIRY_JUDGE_ROLE,
  FORBIDDEN_PARALLEL_STACKS,
  FRAME_TABLE,
  framePriority,
  LEASE_EXPIRY_FIELD,
  LEASE_GENERATION_CANON_FIELD,
  LEASE_GENERATION_FIELD,
  LEASE_ISSUED_FIELD,
  LEASE_REJECT_REASONS,
  LEASE_SEQUENCE_FIELD,
  LEASE_SESSION_FIELD,
  MAX_LEASE_AGE_FIELD,
  PRIORITY_CLASS,
  PUBLIC_HEALTH_FORBIDDEN_FIELDS,
  QUEUE_PROFILES,
  REALTIME_CHANNEL,
  REARM_HANDSHAKE_FRAMES,
  WS_FRAME_TYPES,
  WS_PLAINTEXT_SCHEME,
  WS_ROLES,
  WS_SECURE_SCHEME,
  WS_TAG_SEPARATOR,
  type QueueName,
} from "./envelope";

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");

function loadJson(relativePath: string): Record<string, unknown> {
  return JSON.parse(readFileSync(resolve(REPO_ROOT, relativePath), "utf-8"));
}

// Narrow an unknown JSON node to an indexable object. The frozen files are
// trusted inputs; this keeps the test free of `any` while still traversing them.
function obj(value: unknown): Record<string, unknown> {
  return value as Record<string, unknown>;
}

const ws = loadJson("contracts/ws/envelope.schema.json");
const prim = loadJson("contracts/prim/schema.json");
const frameTypes = obj(ws.frame_types);
const lease = obj(ws.lease);
const queues = obj(ws.queues);
const backpressure = obj(ws.backpressure);
const security = obj(ws.security);
const roles = obj(ws.roles);
const health = obj(ws.health);
const transport = obj(ws.transport);

describe("CTR-WS@v1 mirror equals the frozen envelope", () => {
  it("is CTR-WS@v1 at schema version 1", () => {
    expect(ws.contract).toBe("CTR-WS@v1");
    expect(ws.schema_version).toBe(1);
  });

  it("has exactly the frozen frame-type set", () => {
    expect(new Set(Object.keys(frameTypes))).toEqual(new Set(WS_FRAME_TYPES));
  });

  it("matches every frame's direction, payload, queue, priority, control flag and fields", () => {
    for (const frame of WS_FRAME_TYPES) {
      const spec = FRAME_TABLE[frame];
      const frozen = obj(frameTypes[frame]);
      expect(frozen.direction).toBe(spec.direction);
      expect(frozen.payload).toBe(spec.payload);
      expect(frozen.queue).toBe(spec.queue);
      expect(frozen.priority).toBe(framePriority(frame));
      expect(frozen.control_frame).toBe(spec.isControlFrame);
      expect(frozen.fields).toEqual([...spec.fields]);
    }
    expect(obj(frameTypes.camera).tag_separator).toBe(WS_TAG_SEPARATOR);
  });

  it("transports the lease with the frozen field names and the server as expiry judge", () => {
    expect(lease.expiry_field).toBe(LEASE_EXPIRY_FIELD);
    expect(lease.issued_field).toBe(LEASE_ISSUED_FIELD);
    expect(lease.generation_field).toBe(LEASE_GENERATION_FIELD);
    expect(lease.generation_field_maps_to_canon).toBe(LEASE_GENERATION_CANON_FIELD);
    expect(lease.sequence_field).toBe(LEASE_SEQUENCE_FIELD);
    expect(lease.session_field).toBe(LEASE_SESSION_FIELD);
    expect(lease.expiry_judge_role).toBe(EXPIRY_JUDGE_ROLE);
    expect(obj(lease.age_filter).max_lease_age_field).toBe(MAX_LEASE_AGE_FIELD);
    expect(obj(lease.age_filter).age_input_role).toBe(AGE_INPUT_ROLE);
    expect(lease.reject_reasons).toEqual([...LEASE_REJECT_REASONS]);
    expect(obj(lease.rearm_handshake).frames).toEqual([...REARM_HANDSHAKE_FRAMES]);
  });

  it("keeps the client lease frames free of an expiry field (structural acceptance)", () => {
    expect(lease.client_frame_carries_no_expiry).toBe(true);
    expect(clientLeaseFramesOmitExpiry()).toBe(true);
  });

  it("matches the priority classes, lease-first ordering and queue bindings", () => {
    expect(queues.priority_classes).toEqual(PRIORITY_CLASS);
    expect(queues.lease_is_highest_priority).toBe(true);
    const bindings = obj(queues.bindings);
    for (const frame of WS_FRAME_TYPES) {
      expect(bindings[frame]).toBe(FRAME_TABLE[frame].queue);
    }
  });

  it("matches the bufferedAmount backpressure rule", () => {
    expect(backpressure.signal).toBe("bufferedAmount");
    expect(backpressure.threshold_bytes).toBe(BUFFERED_AMOUNT_THRESHOLD_BYTES);
    expect(backpressure.drop_on_exceed).toEqual([...BACKPRESSURE_DROP_FRAMES]);
    expect(backpressure.protected_frames).toEqual([...BACKPRESSURE_PROTECTED_FRAMES]);
  });

  it("matches the transport, security, roles and health rules", () => {
    expect(transport.realtime_channel).toBe(REALTIME_CHANNEL);
    expect(transport.single_realtime_channel).toBe(true);
    expect(transport.forbidden_parallel_stacks).toEqual([...FORBIDDEN_PARALLEL_STACKS]);
    expect(security.scheme).toBe(WS_SECURE_SCHEME);
    expect(security.plaintext_scheme_forbidden).toBe(WS_PLAINTEXT_SCHEME);
    expect(roles.values).toEqual([...WS_ROLES]);
    expect(roles.control_holder_role).toBe(CONTROL_HOLDER_ROLE);
    expect(roles.observer_may_send_control_frame).toBe(false);
    expect(health.forbidden_fields).toEqual([...PUBLIC_HEALTH_FORBIDDEN_FIELDS]);
  });
});

describe("CTR-PRIM@v1 queue profiles mirror equals the frozen primitive", () => {
  it("matches every bounded queue's capacity, priority, drop policy and classification", () => {
    const profiles = obj(obj(obj(prim.primitives).queue_semantics).profiles);
    expect(new Set(Object.keys(profiles))).toEqual(new Set(Object.keys(QUEUE_PROFILES)));
    for (const name of Object.keys(profiles) as QueueName[]) {
      const mirror = QUEUE_PROFILES[name];
      const frozen = obj(profiles[name]);
      expect(mirror.boundedCapacity).toBe(frozen.bounded_capacity);
      const priorityName = frozen.priority as keyof typeof PRIORITY_CLASS;
      expect(mirror.priority).toBe(PRIORITY_CLASS[priorityName]);
      expect(mirror.dropPolicy).toBe(frozen.drop_policy);
      expect(mirror.dropClassification).toBe(frozen.drop_classification);
    }
  });
});
