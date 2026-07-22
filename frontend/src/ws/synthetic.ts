// Synthetic 3A fixtures for the WS lane — the TypeScript analog of
// `contracts/fixtures`. The GUI never sees real hardware (02d §3): it is verified
// against deterministic frames shaped by the frozen CTR-WS@v1 envelope and the
// CTR-ERR@v1 codes. This module also holds the injected test doubles (a fake
// socket, a fake clock, a synchronous decode port, and a fixture server that
// applies the frozen server-side send authority) so the lane drives WsClient with
// no real WebSocket, Worker or wall clock.
//
// It deliberately imports no decoder: the sync decode port takes the decode
// function as an argument, keeping decode logic out of every non-worker module
// (CG-G-01f).

import {
  authorizeSend,
  cameraFrameTag,
  imageFeatureKey,
  WsAuthorityError,
  type CameraChannel,
  type WsFrameType,
  type WsRole,
} from "./envelope";
import type { SeverityName } from "./errors";
import type {
  DecodedFrame,
  DecoderPort,
  RawFrame,
  Scheduler,
  SocketHandlers,
  SocketLike,
} from "./types";

// A LeRobot-style observation feature set: the state vector, the action, and one
// image key per camera slot. The meter's instrumented target count is derived
// from this list (CG-G-01e), so adding a camera adds a target.
export function observationFeatures(cameraSlots: readonly string[]): string[] {
  return [
    "observation.state",
    "action",
    ...cameraSlots.map((slot) => imageFeatureKey(slot, "rgb")),
  ];
}

export interface LeaseFields {
  sessionId: string;
  generation: number;
  sequence: number;
  expiryMonoServer: number;
  issuedMonoClient: number;
}

export function telemetryFrame(sequence: number): Record<string, unknown> {
  return { type: "telemetry", sequence, observation: { "observation.state": [] } };
}

export function leaseGrantFrame(fields: LeaseFields): Record<string, unknown> {
  return {
    type: "lease_grant",
    session_id: fields.sessionId,
    lease_generation: fields.generation,
    expiry_mono_server: fields.expiryMonoServer,
    sequence: fields.sequence,
    issued_mono_client: fields.issuedMonoClient,
  };
}

export function leaseRejectFrame(
  sessionId: string,
  generation: number,
  reason: string,
): Record<string, unknown> {
  return { type: "lease_reject", session_id: sessionId, lease_generation: generation, reason };
}

export function rearmIssueFrame(sessionId: string, generation: number): Record<string, unknown> {
  return { type: "rearm_issue", session_id: sessionId, lease_generation: generation };
}

export function rearmAcceptFrame(fields: LeaseFields): Record<string, unknown> {
  return {
    type: "rearm_accept",
    session_id: fields.sessionId,
    lease_generation: fields.generation,
    expiry_mono_server: fields.expiryMonoServer,
    sequence: fields.sequence,
    issued_mono_client: fields.issuedMonoClient,
  };
}

export function errorEnvelopeFrame(
  code: string,
  reason: string,
  severity: SeverityName,
): Record<string, unknown> {
  return { code, reason, severity };
}

export function textRaw(frame: Record<string, unknown>): RawFrame {
  return { kind: "text", text: JSON.stringify(frame) };
}

// Build a camera binary frame in the fixture layout:
//   [tag length: uint16 BE][utf-8 `<slot>:<channel>`][image bytes]
export function cameraBinary(slot: string, channel: CameraChannel, image: Uint8Array): ArrayBuffer {
  const tag = new TextEncoder().encode(cameraFrameTag(slot, channel));
  const buffer = new ArrayBuffer(2 + tag.byteLength + image.byteLength);
  const view = new DataView(buffer);
  view.setUint16(0, tag.byteLength, false);
  const bytes = new Uint8Array(buffer);
  bytes.set(tag, 2);
  bytes.set(image, 2 + tag.byteLength);
  return buffer;
}

export function cameraRaw(slot: string, channel: CameraChannel, image: Uint8Array): RawFrame {
  return { kind: "binary", bytes: cameraBinary(slot, channel, image) };
}

// A manual clock and timer wheel. `advance` moves time forward, firing every due
// timer (intervals repeat) in due order, so the renewal loop and socket retry are
// exercised deterministically.
interface FakeTimer {
  id: number;
  due: number;
  handler: () => void;
  interval: number | null;
}

export class FakeScheduler implements Scheduler {
  private mNow: number;
  private mNextId: number;
  private mTimers: Map<number, FakeTimer>;

  constructor() {
    this.mNow = 0;
    this.mNextId = 1;
    this.mTimers = new Map();
  }

  now(): number {
    return this.mNow;
  }

  setTimeout(handler: () => void, ms: number): number {
    const id = this.mNextId++;
    this.mTimers.set(id, { id, due: this.mNow + ms, handler, interval: null });
    return id;
  }

  clearTimeout(id: number): void {
    this.mTimers.delete(id);
  }

  setInterval(handler: () => void, ms: number): number {
    const id = this.mNextId++;
    this.mTimers.set(id, { id, due: this.mNow + ms, handler, interval: ms });
    return id;
  }

  clearInterval(id: number): void {
    this.mTimers.delete(id);
  }

  advance(ms: number): void {
    const target = this.mNow + ms;
    for (;;) {
      let next: FakeTimer | null = null;
      for (const timer of this.mTimers.values()) {
        if (timer.due <= target && (next === null || timer.due < next.due)) {
          next = timer;
        }
      }
      if (next === null) {
        break;
      }
      this.mNow = next.due;
      if (next.interval !== null) {
        next.due = this.mNow + next.interval;
      } else {
        this.mTimers.delete(next.id);
      }
      next.handler();
    }
    this.mNow = target;
  }
}

// A SocketLike that records what the client sent and lets a test inject received
// frames. bufferedAmount is settable to drive the backpressure gate (CG-G-01c).
export class FakeSocket implements SocketLike {
  bufferedAmountValue: number;
  readonly sent: string[];
  closed: boolean;
  private mHandlers: SocketHandlers | null;

  constructor() {
    this.bufferedAmountValue = 0;
    this.sent = [];
    this.closed = false;
    this.mHandlers = null;
  }

  get bufferedAmount(): number {
    return this.bufferedAmountValue;
  }

  send(data: string | ArrayBufferLike | ArrayBufferView): void {
    this.sent.push(typeof data === "string" ? data : "<binary>");
  }

  close(): void {
    this.closed = true;
  }

  setHandlers(handlers: SocketHandlers): void {
    this.mHandlers = handlers;
  }

  emitOpen(): void {
    this.mHandlers?.onOpen();
  }

  emitClose(): void {
    this.mHandlers?.onClose();
  }

  emitError(error: unknown): void {
    this.mHandlers?.onError(error);
  }

  receive(raw: RawFrame): void {
    if (raw.kind === "text") {
      this.mHandlers?.onMessage(raw.text);
    } else {
      this.mHandlers?.onMessage(raw.bytes);
    }
  }
}

// A factory that counts sockets built, so a test can assert exactly one realtime
// channel exists (CG-G-01a).
export class CountingSocketFactory {
  readonly sockets: FakeSocket[];

  constructor() {
    this.sockets = [];
  }

  // The URL is ignored: the fixture socket needs no address. A zero-arg impl is
  // assignable to WebSocketFactory (fewer parameters is allowed).
  readonly build = (): SocketLike => {
    const socket = new FakeSocket();
    this.sockets.push(socket);
    return socket;
  };

  get count(): number {
    return this.sockets.length;
  }

  latest(): FakeSocket {
    return this.sockets[this.sockets.length - 1];
  }
}

// A DecoderPort that decodes synchronously using an injected decode function. The
// function comes from a test that imports the real decoder, so decode logic still
// lives only on the worker side of the boundary in production code (CG-G-01f).
export class SyncDecoderPort implements DecoderPort {
  private mDecode: (raw: RawFrame) => DecodedFrame;
  private mHandler: ((frame: DecodedFrame) => void) | null;

  constructor(decode: (raw: RawFrame) => DecodedFrame) {
    this.mDecode = decode;
    this.mHandler = null;
  }

  decode(raw: RawFrame): void {
    const frame = this.mDecode(raw);
    this.mHandler?.(frame);
  }

  onDecoded(handler: (frame: DecodedFrame) => void): void {
    this.mHandler = handler;
  }

  dispose(): void {
    this.mHandler = null;
  }
}

// The fixture server's send-authority decision. It applies the FROZEN server rule
// (authorize_send) to a client frame, so an observer's control send is refused
// server-side — client-side hiding is not what makes it safe (CG-G-01g).
export interface ServerDecision {
  accepted: boolean;
  reason: string | null;
}

export function fixtureServerAuthorize(role: WsRole, frameType: WsFrameType): ServerDecision {
  try {
    authorizeSend(role, frameType);
    return { accepted: true, reason: null };
  } catch (error) {
    if (error instanceof WsAuthorityError) {
      return { accepted: false, reason: "control authority denied" };
    }
    throw error;
  }
}
