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
import { isHandshakeRefusal, isServerRefusal, type LinkRefusal } from "./closeCodes";
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

// The one client frame whose loss may go unthrown when there is no socket.
//
// Two reasons, and both have to hold — a frame is only silent-tolerant if losing it
// is already handled AND throwing would land somewhere nobody can catch:
//   1. Renewal absence IS expiry (`leaseRenewer.ts`). A renewal that never arrives
//      is the server's signal to expire the lease and hold the arm, so a dropped
//      renewal reaches the same outcome as a delivered refusal — it fails safe.
//   2. `LeaseRenewer.tick()` emits it from a `setInterval`. A throw there escapes
//      into the scheduler with no caller on the stack, once per interval for as
//      long as the socket is down.
//
// Every other client frame was sent because something asked for it, and the asker
// is owed an answer. `rearm_confirm` is deliberately NOT here: it comes from
// `confirmRearm()`, an operator action, and a silently dropped resume leaves them
// pressing a button that does nothing.
const EXPIRY_COVERED_FRAME: WsFrameType = "lease_renew";

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
  // The socket was closed by a server refusal. Called once per refusal, and the socket is
  // not retried afterwards — the caller is the only thing that can act on it.
  onLinkRefused?: (refusal: LinkRefusal) => void;
}

export interface WsClientStats {
  socketCount: number;
  socketGeneration: number;
  backpressureDrops: number;
  malformedCount: number;
  errorCount: number;
  socketErrorCount: number;
  // Closes carrying a server refusal code. Distinct from `socketErrorCount`, which counts
  // browser-side transport errors: one says the server refused this connection, the other
  // says the browser's socket faulted, and they call for opposite responses.
  refusalCount: number;
  // Frames that reached no socket at all. Counted even when `send` also throws, so
  // a tolerated drop is still visible; distinct from `backpressureDrops`, which
  // counts frames shed by the frozen rule while a socket was open.
  undeliverableCount: number;
}

// Raised by `send` when a frame could not be handed to a socket because there is
// none open. This is NOT backpressure: a full buffer still has a transport, and the
// frozen rule decides whether that frame is queued or shed. Here the frame reached
// nothing, and the socket retry does not replay it — a caller that needs the frame
// delivered has to send it again.
export class WsSendUndeliverableError extends Error {
  readonly frameType: WsFrameType;

  constructor(frameType: WsFrameType) {
    super(
      `frame '${frameType}' was not sent: no open WebSocket. It was not queued and ` +
        `the socket retry will not replay it; the caller must re-send`,
    );
    this.name = "WsSendUndeliverableError";
    this.frameType = frameType;
  }
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
      socket.onclose = (event: CloseEvent) => handlers.onClose(event.code, event.reason);
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
    "onTelemetry" | "onCamera" | "onLeaseFrame" | "onError" | "onLinkRefused"
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
  private mRefusalCount: number;
  private mUndeliverableCount: number;

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
      onLinkRefused: options.onLinkRefused,
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
    this.mRefusalCount = 0;
    this.mUndeliverableCount = 0;

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
      refusalCount: this.mRefusalCount,
      undeliverableCount: this.mUndeliverableCount,
    };
  }

  // Send one frame, or fail loudly. Returning normally means the frame was handed to
  // an open socket; the two ways it does not are both signalled, never swallowed:
  //
  //   - the role may not send this frame -> WsAuthorityError (the frozen
  //     authorize_send rule, mirrored here as defence in depth; the authoritative
  //     rejection is still the server's, this just keeps the browser from trying).
  //   - there is no open socket -> WsSendUndeliverableError, except for
  //     EXPIRY_COVERED_FRAME, which is counted only. See that constant for why one
  //     frame is exempt and why nothing else is.
  //
  // A silent return on an absent socket is what this used to do, and under CTR-WS@v2
  // this method is the stop path: `stop_hold` travels through here, so a quiet drop
  // would let an operator press STOP_HOLD against a closed socket and be told
  // nothing. NORM-007 already ruled that a stop reaching nothing is worse than no
  // stop, because it is indistinguishable from one that worked.
  send(frameType: WsFrameType, frame: Record<string, unknown>): void {
    authorizeSend(this.mRole, frameType);
    if (!this.mSocket) {
      // Counted on both branches: a tolerated drop is still a drop, and stats() is
      // where this module already reports what it could not do.
      this.mUndeliverableCount += 1;
      if (frameType !== EXPIRY_COVERED_FRAME) {
        throw new WsSendUndeliverableError(frameType);
      }
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
      onClose: (code, reason) => this.onSocketClose(code, reason),
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
  //
  // A HANDSHAKE refusal is the one exception, and only that one. The server settles the
  // role, the session and the Origin before it reads a frame, and all three are fixed
  // when this client is constructed — so the next socket earns the identical close and
  // the retry is a request-per-delay loop that never ends. There the client quiesces and
  // hands the refusal out; `dispose()` because a half-live client whose pump and renewal
  // loop keep running against a null socket is the same silence in another shape.
  //
  // Every other refusal is a verdict on ONE FRAME (`backend/ws/dispatch.py`,
  // `arm_channel.py`), and a fresh socket that does not send it is accepted. Those are
  // counted and retried, because this socket carries the soft stop and `FR-GUI-065` puts
  // that within reach of every role — killing the channel over one refused `command`
  // would take the stop away until the operator reloads the page.
  private onSocketClose(code: number, reason: string): void {
    this.mSocket = null;
    if (isServerRefusal(code)) {
      this.mRefusalCount += 1;
    }
    if (isHandshakeRefusal(code)) {
      this.dispose();
      this.mCallbacks.onLinkRefused?.({ code, reason });
      return;
    }
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
