// The dead-man lease renewal loop. The GUI TRANSPORTS and RENEWS the WP-2A-02
// lease; it does NOT redefine it. The browser periodically sends lease_renew
// frames carrying only the frozen client-frame fields — and a client frame never
// carries the expiry field, so the SERVER clock stays the sole expiry judge
// (structural). Renewal absence is expiry: on a reject the loop STOPS, and motion
// resumes only through the server-driven re-arm handshake, never a resent renewal.
// An observer downgrade stops the loop — an observer holds no renewal right.

import {
  FRAME_TABLE,
  LEASE_EXPIRY_FIELD,
  LEASE_GENERATION_FIELD,
  LEASE_ISSUED_FIELD,
  LEASE_REASON_FIELD,
  LEASE_SEQUENCE_FIELD,
  LEASE_SESSION_FIELD,
  type WsFrameType,
} from "./envelope";
import type { Scheduler } from "./types";

export type LeaseStatus = "unknown" | "held" | "latched" | "rearming" | "observer";

export interface LeaseSnapshot {
  status: LeaseStatus;
  sessionId: string | null;
  generation: number | null;
  sequence: number;
  // Last granted expiry, on the SERVER clock, for display only — the browser
  // never judges expiry against it.
  expiryMonoServer: number | null;
  lastRejectReason: string | null;
}

// Sends one client lease/re-arm frame, already authorized by the client. The
// renewer only ever asks to send control frames while it holds the lease.
export type SendLeaseFrame = (frameType: WsFrameType, frame: Record<string, unknown>) => void;

export class LeaseRenewer {
  private mSend: SendLeaseFrame;
  private mScheduler: Scheduler;
  private mRenewIntervalMs: number;
  private mStatus: LeaseStatus;
  private mSessionId: string | null;
  private mGeneration: number | null;
  private mSequence: number;
  private mExpiryMonoServer: number | null;
  private mLastRejectReason: string | null;
  private mTimerId: number | null;

  constructor(send: SendLeaseFrame, scheduler: Scheduler, renewIntervalMs: number) {
    this.mSend = send;
    this.mScheduler = scheduler;
    this.mRenewIntervalMs = renewIntervalMs;
    this.mStatus = "unknown";
    this.mSessionId = null;
    this.mGeneration = null;
    this.mSequence = 0;
    this.mExpiryMonoServer = null;
    this.mLastRejectReason = null;
    this.mTimerId = null;
  }

  snapshot(): LeaseSnapshot {
    return {
      status: this.mStatus,
      sessionId: this.mSessionId,
      generation: this.mGeneration,
      sequence: this.mSequence,
      expiryMonoServer: this.mExpiryMonoServer,
      lastRejectReason: this.mLastRejectReason,
    };
  }

  // Route one decoded lease-class text frame. Unknown text frames are ignored here.
  handleLeaseFrame(frameType: WsFrameType, body: Record<string, unknown>): void {
    switch (frameType) {
      case "lease_grant":
        this.onGrant(body);
        break;
      case "lease_reject":
        this.onReject(body);
        break;
      case "rearm_issue":
        this.onRearmIssue(body);
        break;
      case "rearm_accept":
        this.onRearmAccept(body);
        break;
      default:
        break;
    }
  }

  private onGrant(body: Record<string, unknown>): void {
    this.mSessionId = asString(body[LEASE_SESSION_FIELD]) ?? this.mSessionId;
    this.mGeneration = asNumber(body[LEASE_GENERATION_FIELD]) ?? this.mGeneration;
    this.mSequence = asNumber(body[LEASE_SEQUENCE_FIELD]) ?? this.mSequence;
    this.mExpiryMonoServer = asNumber(body[LEASE_EXPIRY_FIELD]) ?? this.mExpiryMonoServer;
    if (this.mStatus !== "observer") {
      this.mStatus = "held";
      this.startLoop();
    }
  }

  private onReject(body: Record<string, unknown>): void {
    // Renewal absence is expiry: latch and stop renewing. Only the re-arm
    // handshake resumes motion; a resent renewal never does.
    this.mLastRejectReason = asString(body[LEASE_REASON_FIELD]) ?? "rejected";
    this.mStatus = "latched";
    this.stopLoop();
  }

  private onRearmIssue(body: Record<string, unknown>): void {
    this.mGeneration = asNumber(body[LEASE_GENERATION_FIELD]) ?? this.mGeneration;
    this.mStatus = "rearming";
    this.stopLoop();
  }

  private onRearmAccept(body: Record<string, unknown>): void {
    this.mGeneration = asNumber(body[LEASE_GENERATION_FIELD]) ?? this.mGeneration;
    this.mSequence = asNumber(body[LEASE_SEQUENCE_FIELD]) ?? this.mSequence;
    this.mExpiryMonoServer = asNumber(body[LEASE_EXPIRY_FIELD]) ?? this.mExpiryMonoServer;
    this.mLastRejectReason = null;
    if (this.mStatus !== "observer") {
      this.mStatus = "held";
      this.startLoop();
    }
  }

  // Operator confirms a re-arm the server issued. This is the only client action
  // that resumes a latched lease, and it carries no expiry field.
  confirmRearm(): void {
    if (this.mStatus !== "rearming") {
      return;
    }
    this.emit("rearm_confirm");
  }

  // Downgrade to observer: stop renewing and hold no renewal right. Control sends
  // are refused server-side by role; the loop simply stops emitting them.
  downgradeToObserver(): void {
    this.mStatus = "observer";
    this.stopLoop();
  }

  stop(): void {
    this.stopLoop();
  }

  private startLoop(): void {
    if (this.mTimerId !== null) {
      return;
    }
    this.mTimerId = this.mScheduler.setInterval(() => this.tick(), this.mRenewIntervalMs);
  }

  private stopLoop(): void {
    if (this.mTimerId !== null) {
      this.mScheduler.clearInterval(this.mTimerId);
      this.mTimerId = null;
    }
  }

  private tick(): void {
    if (this.mStatus !== "held") {
      return;
    }
    this.mSequence += 1;
    this.emit("lease_renew");
  }

  // Build a client lease frame from ONLY the frozen field set for its type, then
  // send it. Because the expiry field is absent from every client frame's field
  // list, it can never be assembled here — the browser cannot author an expiry.
  private emit(frameType: WsFrameType): void {
    const values: Record<string, unknown> = {
      [LEASE_SESSION_FIELD]: this.mSessionId,
      [LEASE_GENERATION_FIELD]: this.mGeneration,
      [LEASE_SEQUENCE_FIELD]: this.mSequence,
      [LEASE_ISSUED_FIELD]: this.mScheduler.now(),
    };
    const frame: Record<string, unknown> = { type: frameType };
    for (const field of FRAME_TABLE[frameType].fields) {
      frame[field] = values[field];
    }
    this.mSend(frameType, frame);
  }
}

function asString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
