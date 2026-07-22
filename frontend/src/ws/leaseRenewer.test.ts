// The dead-man lease renewal loop: it renews on a cadence, carries no expiry
// field on any client frame (the server clock stays the sole expiry judge),
// latches and stops on a reject, resumes only through the re-arm handshake, and
// stops entirely on an observer downgrade.

import { describe, expect, it } from "vitest";

import { LeaseRenewer, type LeaseSnapshot } from "./leaseRenewer";
import {
  FakeScheduler,
  leaseGrantFrame,
  leaseRejectFrame,
  rearmAcceptFrame,
  rearmIssueFrame,
} from "./synthetic";
import type { WsFrameType } from "./envelope";

const RENEW_MS = 100;

interface SentFrame {
  frameType: WsFrameType;
  frame: Record<string, unknown>;
}

function setup() {
  const scheduler = new FakeScheduler();
  const sent: SentFrame[] = [];
  const renewer = new LeaseRenewer((frameType, frame) => sent.push({ frameType, frame }), scheduler, RENEW_MS);
  return { scheduler, sent, renewer };
}

function grant(sequence: number) {
  return leaseGrantFrame({
    sessionId: "sess-1",
    generation: 3,
    sequence,
    expiryMonoServer: 500000,
    issuedMonoClient: 0,
  });
}

describe("LeaseRenewer", () => {
  it("renews on a cadence with a monotonically increasing sequence and no expiry field", () => {
    const { scheduler, sent, renewer } = setup();
    renewer.handleLeaseFrame("lease_grant", grant(5));

    scheduler.advance(3 * RENEW_MS);

    expect(sent).toHaveLength(3);
    const sequences = sent.map((entry) => entry.frame.sequence);
    expect(sequences).toEqual([6, 7, 8]);
    for (const entry of sent) {
      expect(entry.frameType).toBe("lease_renew");
      expect(entry.frame).toHaveProperty("session_id", "sess-1");
      expect(entry.frame).toHaveProperty("issued_mono_client");
      // Structural: a client lease frame never carries an expiry.
      expect(entry.frame).not.toHaveProperty("expiry_mono_server");
    }
  });

  it("latches and stops renewing on a reject", () => {
    const { scheduler, sent, renewer } = setup();
    renewer.handleLeaseFrame("lease_grant", grant(5));
    scheduler.advance(RENEW_MS);
    const afterFirst = sent.length;

    renewer.handleLeaseFrame("lease_reject", leaseRejectFrame("sess-1", 3, "rejected_stale_generation"));
    scheduler.advance(5 * RENEW_MS);

    expect(sent.length).toBe(afterFirst);
    const snapshot: LeaseSnapshot = renewer.snapshot();
    expect(snapshot.status).toBe("latched");
    expect(snapshot.lastRejectReason).toBe("rejected_stale_generation");
  });

  it("resumes only through the re-arm handshake, never a resent renewal", () => {
    const { scheduler, sent, renewer } = setup();
    renewer.handleLeaseFrame("lease_grant", grant(5));
    renewer.handleLeaseFrame("lease_reject", leaseRejectFrame("sess-1", 3, "rejected_latched"));

    renewer.handleLeaseFrame("rearm_issue", rearmIssueFrame("sess-1", 4));
    expect(renewer.snapshot().status).toBe("rearming");
    scheduler.advance(5 * RENEW_MS);
    // A latched/rearming lease sends nothing until the operator confirms.
    expect(sent.every((entry) => entry.frameType !== "lease_renew" || entry.frame.sequence === undefined)).toBe(true);
    const beforeConfirm = sent.length;

    renewer.confirmRearm();
    const confirm = sent[sent.length - 1];
    expect(confirm.frameType).toBe("rearm_confirm");
    expect(confirm.frame).not.toHaveProperty("expiry_mono_server");
    expect(sent.length).toBe(beforeConfirm + 1);

    renewer.handleLeaseFrame(
      "rearm_accept",
      rearmAcceptFrame({ sessionId: "sess-1", generation: 4, sequence: 20, expiryMonoServer: 9, issuedMonoClient: 0 }),
    );
    expect(renewer.snapshot().status).toBe("held");
    scheduler.advance(RENEW_MS);
    const resumed = sent[sent.length - 1];
    expect(resumed.frameType).toBe("lease_renew");
    expect(resumed.frame.sequence).toBe(21);
  });

  it("stops renewing on an observer downgrade", () => {
    const { scheduler, sent, renewer } = setup();
    renewer.handleLeaseFrame("lease_grant", grant(5));
    scheduler.advance(RENEW_MS);
    const afterFirst = sent.length;

    renewer.downgradeToObserver();
    scheduler.advance(5 * RENEW_MS);

    expect(sent.length).toBe(afterFirst);
    expect(renewer.snapshot().status).toBe("observer");
  });
});
