// WsClient — the ONE realtime WebSocket (D-2, CG-G-01a). It owns exactly one
// socket at a time, hands every raw message to the decode worker (no main-thread
// decode, CG-G-01f), routes decoded frames through class-based bounded queues
// drained in priority order (lease first, CG-G-01b), sheds camera frames under
// bufferedAmount backpressure while protecting lease/command/telemetry
// (CG-G-01c), runs the dead-man lease renewal loop, and refuses an observer's
// control send by the frozen server rule (CG-G-01g).
//
// It NEVER re-attaches the backend Robot. On a socket close it retries the SOCKET
// only, through a timer backoff; there is no reconnect control and no path that
// would make the backend re-run connect()/set_zero_position() (I-2, CG-G-01d).

import {
  authorizeSend,
  imageFeatureKey,
  isImageFeatureKey,
  shouldDropUnderBackpressure,
  WS_PLAINTEXT_SCHEME,
  WS_SECURE_SCHEME,
  type WsFrameType,
  type WsRole,
} from "./envelope";
import type { ErrorEnvelope } from "./errors";
import { LeaseRenewer } from "./leaseRenewer";
import { PriorityDispatcher } from "./boundedQueue";
import { instrumentedChannels, StreamMeter } from "./streamMeter";
import {
  systemScheduler,
  type DecodedCameraFrame,
  type DecodedFrame,
  type DecodedTextFrame,
  type DecoderPort,
  type Scheduler,
  type SocketLike,
  type WebSocketFactory,
} from "./types";

const DEFAULT_RENEW_INTERVAL_MS = 250;
const DEFAULT_RETRY_DELAY_MS = 1000;
const DEFAULT_PUMP_INTERVAL_MS = 16;

// The receive-side queue classes. Command is client_to_server only, so it is
// never received; the client holds the three classes it actually consumes.
const RECEIVE_QUEUE_CLASSES = ["lease", "telemetry", "camera_preview"] as const;

const LEASE_FRAME_TYPES: readonly WsFrameType[] = [
  "lease_grant",
  "lease_reject",
  "rearm_issue",
  "rearm_accept",
];

export interface WsClientOptions {
  url: string;
  socketFactory: WebSocketFactory;
  decoderPort: DecoderPort;
  scheduler?: Scheduler;
  role?: WsRole;
  observationFeatures?: readonly string[];
  renewIntervalMs?: number;
  retryDelayMs?: number;
  pumpIntervalMs?: number;
  onTelemetry?: (frame: DecodedTextFrame) => void;
  onCamera?: (frame: DecodedCameraFrame) => void;
  onLeaseFrame?: (frame: DecodedTextFrame) => void;
  onError?: (error: ErrorEnvelope) => void;
}

export interface WsClientStats {
  socketCount: number;
  socketGeneration: number;
  backpressureDrops: number;
  malformedCount: number;
  errorCount: number;
  socketErrorCount: number;
}

// Derive the same-origin WS URL from the page location: wss when the page is
// https, ws otherwise. Same-origin only — the air-gap forbids any external origin.
export function resolveWsUrl(location: { protocol: string; host: string }, path: string): string {
  const scheme = location.protocol === "https:" ? WS_SECURE_SCHEME : WS_PLAINTEXT_SCHEME;
  return `${scheme}://${location.host}${path}`;
}

// The production socket factory: wrap a real WebSocket into SocketLike. Binary is
// received as ArrayBuffer so the decode worker can transfer it zero-copy.
export function browserWebSocketFactory(url: string): SocketLike {
  const socket = new WebSocket(url);
  socket.binaryType = "arraybuffer";
  return {
    send: (data) => socket.send(data),
    close: () => socket.close(),
    get bufferedAmount() {
      return socket.bufferedAmount;
    },
    setHandlers: (handlers) => {
      socket.onopen = () => handlers.onOpen();
      socket.onmessage = (event: MessageEvent) => handlers.onMessage(event.data);
      socket.onclose = () => handlers.onClose();
      socket.onerror = (event) => handlers.onError(event);
    },
  };
}

export class WsClient {
  private mUrl: string;
  private mSocketFactory: WebSocketFactory;
  private mDecoderPort: DecoderPort;
  private mScheduler: Scheduler;
  private mRole: WsRole;
  private mObservationFeatures: readonly string[];
  private mRenewIntervalMs: number;
  private mRetryDelayMs: number;
  private mPumpIntervalMs: number;
  private mCallbacks: Pick<
    WsClientOptions,
    "onTelemetry" | "onCamera" | "onLeaseFrame" | "onError"
  >;

  private mSocket: SocketLike | null;
  private mSocketGeneration: number;
  private mDispatcher: PriorityDispatcher<DecodedTextFrame | DecodedCameraFrame>;
  private mMeter: StreamMeter;
  private mRenewer: LeaseRenewer;
  private mPumpTimerId: number | null;
  private mRetryTimerId: number | null;
  private mStarted: boolean;

  private mBackpressureDrops: number;
  private mMalformedCount: number;
  private mErrorCount: number;
  private mSocketErrorCount: number;

  constructor(options: WsClientOptions) {
    this.mUrl = options.url;
    this.mSocketFactory = options.socketFactory;
    this.mDecoderPort = options.decoderPort;
    this.mScheduler = options.scheduler ?? systemScheduler;
    this.mRole = options.role ?? "observer";
    this.mObservationFeatures = options.observationFeatures ?? [];
    this.mRenewIntervalMs = options.renewIntervalMs ?? DEFAULT_RENEW_INTERVAL_MS;
    this.mRetryDelayMs = options.retryDelayMs ?? DEFAULT_RETRY_DELAY_MS;
    this.mPumpIntervalMs = options.pumpIntervalMs ?? DEFAULT_PUMP_INTERVAL_MS;
    this.mCallbacks = {
      onTelemetry: options.onTelemetry,
      onCamera: options.onCamera,
      onLeaseFrame: options.onLeaseFrame,
      onError: options.onError,
    };

    this.mSocket = null;
    this.mSocketGeneration = 0;
    this.mDispatcher = new PriorityDispatcher([...RECEIVE_QUEUE_CLASSES]);
    this.mMeter = new StreamMeter(instrumentedChannels(this.mObservationFeatures));
    this.mRenewer = new LeaseRenewer(
      (frameType, frame) => this.send(frameType, frame),
      this.mScheduler,
      this.mRenewIntervalMs,
    );
    this.mPumpTimerId = null;
    this.mRetryTimerId = null;
    this.mStarted = false;

    this.mBackpressureDrops = 0;
    this.mMalformedCount = 0;
    this.mErrorCount = 0;
    this.mSocketErrorCount = 0;

    this.mDecoderPort.onDecoded((frame) => this.onDecoded(frame));
  }

  // Open the one socket and begin draining. Idempotent — a second call is a no-op,
  // so nothing can open a parallel realtime channel.
  start(): void {
    if (this.mStarted) {
      return;
    }
    this.mStarted = true;
    this.openSocket();
    this.mPumpTimerId = this.mScheduler.setInterval(() => this.pump(), this.mPumpIntervalMs);
  }

  // Tear down: close the single socket, stop the loops, release the worker. This
  // ends the browser session's transport; it never signals the backend Robot.
  dispose(): void {
    this.mStarted = false;
    if (this.mPumpTimerId !== null) {
      this.mScheduler.clearInterval(this.mPumpTimerId);
      this.mPumpTimerId = null;
    }
    if (this.mRetryTimerId !== null) {
      this.mScheduler.clearTimeout(this.mRetryTimerId);
      this.mRetryTimerId = null;
    }
    this.mRenewer.stop();
    this.closeSocket();
    this.mDecoderPort.dispose();
  }

  get lease() {
    return this.mRenewer;
  }

  get meter(): StreamMeter {
    return this.mMeter;
  }

  role(): WsRole {
    return this.mRole;
  }

  stats(): WsClientStats {
    return {
      socketCount: this.mSocket ? 1 : 0,
      socketGeneration: this.mSocketGeneration,
      backpressureDrops: this.mBackpressureDrops,
      malformedCount: this.mMalformedCount,
      errorCount: this.mErrorCount,
      socketErrorCount: this.mSocketErrorCount,
    };
  }

  // Send one frame. The frozen server rule (authorize_send) is mirrored here as
  // defence in depth: an observer may not send a control frame. The authoritative
  // rejection is the server's; this refusal keeps the browser from even trying.
  send(frameType: WsFrameType, frame: Record<string, unknown>): void {
    authorizeSend(this.mRole, frameType);
    if (!this.mSocket) {
      return;
    }
    this.mSocket.send(JSON.stringify(frame));
  }

  // Promote to operator once the server has granted command authority. The lease
  // grant that follows starts the renewal loop.
  promoteToOperator(): void {
    this.mRole = "operator";
  }

  // The observer-downgrade path: drop command authority, stop renewing. Control
  // sends are refused by role from here on; the lease loop no longer emits frames.
  downgradeToObserver(): void {
    this.mRole = "observer";
    this.mRenewer.downgradeToObserver();
  }

  private openSocket(): void {
    this.closeSocket();
    const socket = this.mSocketFactory(this.mUrl);
    this.mSocket = socket;
    this.mSocketGeneration += 1;
    socket.setHandlers({
      onOpen: () => {},
      onMessage: (data) => this.onSocketMessage(data),
      onClose: () => this.onSocketClose(),
      // A socket transport error is a browser-side event, not a backend OA fault,
      // so it is counted here and never surfaced as a fabricated OA-* envelope.
      onError: () => {
        this.mSocketErrorCount += 1;
      },
    });
  }

  private closeSocket(): void {
    if (this.mSocket) {
      this.mSocket.close();
      this.mSocket = null;
    }
  }

  // A closed socket is retried — the socket, and only the socket. The backend
  // Robot is untouched (I-2): there is no re-attach here, by construction.
  private onSocketClose(): void {
    this.mSocket = null;
    if (!this.mStarted || this.mRetryTimerId !== null) {
      return;
    }
    this.mRetryTimerId = this.mScheduler.setTimeout(() => {
      this.mRetryTimerId = null;
      if (this.mStarted) {
        this.openSocket();
      }
    }, this.mRetryDelayMs);
  }

  // Hand the raw message straight to the decode worker. The main thread inspects
  // nothing here — string vs binary is the only branch, and it is transport, not
  // decode (CG-G-01f).
  private onSocketMessage(data: string | ArrayBuffer): void {
    if (typeof data === "string") {
      this.mDecoderPort.decode({ kind: "text", text: data });
    } else {
      this.mDecoderPort.decode({ kind: "binary", bytes: data });
    }
  }

  private onDecoded(frame: DecodedFrame): void {
    switch (frame.payload) {
      case "malformed":
        this.mMalformedCount += 1;
        return;
      case "error":
        this.mErrorCount += 1;
        this.mCallbacks.onError?.(frame.error);
        return;
      default:
        this.ingress(frame);
    }
  }

  // Backpressure gate then enqueue. Above the bufferedAmount threshold a camera
  // frame is shed and counted; lease, telemetry and command are always admitted.
  private ingress(frame: DecodedTextFrame | DecodedCameraFrame): void {
    const bufferedAmount = this.mSocket?.bufferedAmount ?? 0;
    if (shouldDropUnderBackpressure(frame.frameType, bufferedAmount)) {
      this.mBackpressureDrops += 1;
      if (frame.payload === "binary") {
        this.mMeter.markDrop(imageFeatureKey(frame.slot, frame.channel));
      }
      return;
    }
    this.mDispatcher.enqueueFrame(frame.frameType, frame);
  }

  // Drain every class in priority order. A camera flood cannot delay this because
  // lease and telemetry drain first and the camera queue is bounded.
  pump(): void {
    this.mDispatcher.drain((_queue, frame) => this.deliver(frame));
  }

  private deliver(frame: DecodedTextFrame | DecodedCameraFrame): void {
    if (frame.payload === "binary") {
      this.mMeter.mark(imageFeatureKey(frame.slot, frame.channel), this.mScheduler.now());
      this.mCallbacks.onCamera?.(frame);
      return;
    }
    if (LEASE_FRAME_TYPES.includes(frame.frameType)) {
      this.mRenewer.handleLeaseFrame(frame.frameType, frame.body);
      this.mCallbacks.onLeaseFrame?.(frame);
      return;
    }
    // Telemetry: one frame refreshes every non-image observation channel at once.
    const now = this.mScheduler.now();
    for (const feature of this.mObservationFeatures) {
      if (!isImageFeatureKey(feature)) {
        this.mMeter.mark(feature, now);
      }
    }
    this.mCallbacks.onTelemetry?.(frame);
  }
}
