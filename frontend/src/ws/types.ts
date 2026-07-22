// Shared shapes and injection seams for the WS client. Every external dependency
// the client touches — the socket, the decode worker, the clock/timers — is an
// interface here so the vitest lane drives the client deterministically against
// the 3A synthetic fixtures, with no real WebSocket, Worker, or wall clock.

import type { ErrorEnvelope } from "./errors";
import type { CameraChannel, WsFrameType } from "./envelope";

// A raw WS message before decode. The client hands one of these to the decode
// worker and never inspects its contents on the main thread (CG-G-01f).
export type RawFrame =
  | { kind: "text"; text: string }
  | { kind: "binary"; bytes: ArrayBuffer };

// A decoded envelope, produced only inside the decode worker.
export type DecodedFrame =
  | DecodedTextFrame
  | DecodedCameraFrame
  | DecodedErrorFrame
  | DecodedMalformedFrame;

export interface DecodedTextFrame {
  payload: "text";
  frameType: WsFrameType;
  body: Record<string, unknown>;
}

export interface DecodedCameraFrame {
  payload: "binary";
  frameType: "camera";
  slot: string;
  channel: CameraChannel;
  bytes: Uint8Array;
}

// An error envelope the server sent, carrying a registered OA-* code. Carried as
// data, never thrown, so one error frame never tears down the single socket.
export interface DecodedErrorFrame {
  payload: "error";
  error: ErrorEnvelope;
}

// A frame the decoder could not parse. It fabricates no OA-* code — a decode
// failure is a browser-side event, not a registered backend fault — and the
// client counts it and moves on.
export interface DecodedMalformedFrame {
  payload: "malformed";
  reason: string;
}

// The subset of WebSocket the client uses. The production factory wraps a real
// WebSocket into this shape; a test injects a fake. bufferedAmount is the
// backpressure signal (CG-G-01c).
export interface SocketLike {
  send(data: string | ArrayBufferLike | ArrayBufferView): void;
  close(): void;
  readonly bufferedAmount: number;
  setHandlers(handlers: SocketHandlers): void;
}

export interface SocketHandlers {
  onOpen(): void;
  onMessage(data: string | ArrayBuffer): void;
  onClose(): void;
  onError(error: unknown): void;
}

// Builds the one socket. The client calls this exactly once per session and
// re-invokes it only to retry the socket itself — never to re-attach the backend
// Robot (that would destroy zeroing; there is no such path here).
export type WebSocketFactory = (url: string) => SocketLike;

// The decode boundary. The main thread posts raw frames in and receives decoded
// frames out; all parsing happens on the worker side of this port (CG-G-01f).
export interface DecoderPort {
  decode(raw: RawFrame): void;
  onDecoded(handler: (frame: DecodedFrame) => void): void;
  dispose(): void;
}

// Timers and the client monotonic clock, injected so the renewal loop and the
// socket-retry backoff are deterministic under test.
export interface Scheduler {
  setInterval(handler: () => void, ms: number): number;
  clearInterval(id: number): void;
  setTimeout(handler: () => void, ms: number): number;
  clearTimeout(id: number): void;
  // A monotonic client-clock reading in milliseconds. It is an age input only;
  // the SERVER clock is the sole expiry judge (CTR-PRIM@v1).
  now(): number;
}

// The system scheduler used in the browser. now() prefers the monotonic
// performance clock and falls back to Date for environments without it.
export const systemScheduler: Scheduler = {
  setInterval: (handler, ms) => globalThis.setInterval(handler, ms) as unknown as number,
  clearInterval: (id) => globalThis.clearInterval(id),
  setTimeout: (handler, ms) => globalThis.setTimeout(handler, ms) as unknown as number,
  clearTimeout: (id) => globalThis.clearTimeout(id),
  now: () =>
    typeof globalThis.performance?.now === "function"
      ? globalThis.performance.now()
      : Date.now(),
};
