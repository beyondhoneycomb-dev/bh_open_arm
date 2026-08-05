// The WsClient runtime gates: one realtime socket (CG-G-01a), a camera flood that
// does not delay lease/telemetry (CG-G-01b), bufferedAmount backpressure shedding
// camera while protecting command/telemetry (CG-G-01c), and an observer's control
// send refused server-side (CG-G-01g). The socket retry is WS-only — it never
// re-attaches the backend Robot.

import { describe, expect, it, vi } from "vitest";

import { decodeFrame } from "./decoder";
import { BUFFERED_AMOUNT_THRESHOLD_BYTES, imageFeatureKey, WsAuthorityError } from "./envelope";
import {
  CountingSocketFactory,
  FakeScheduler,
  cameraRaw,
  fixtureServerAuthorize,
  leaseGrantFrame,
  observationFeatures,
  rearmIssueFrame,
  SyncDecoderPort,
  telemetryFrame,
  textRaw,
} from "./synthetic";
import { WsClient, WsSendUndeliverableError, type WsClientOptions } from "./wsClient";

const NEVER_PUMP_MS = 1_000_000;

function makeClient(overrides: Partial<WsClientOptions> = {}) {
  const factory = new CountingSocketFactory();
  const scheduler = new FakeScheduler();
  const client = new WsClient({
    url: "ws://backend.local/ws",
    socketFactory: factory.build,
    decoderPort: new SyncDecoderPort(decodeFrame),
    scheduler,
    role: "operator",
    observationFeatures: observationFeatures(["left_wrist", "right_wrist"]),
    pumpIntervalMs: NEVER_PUMP_MS,
    ...overrides,
  });
  return { client, factory, scheduler };
}

describe("CG-G-01a exactly one realtime socket", () => {
  it("opens exactly one socket on start and holds one at a time", () => {
    const { client, factory } = makeClient();
    client.start();
    expect(factory.count).toBe(1);
    expect(client.stats().socketCount).toBe(1);
    // A second start is a no-op — nothing can open a parallel realtime channel.
    client.start();
    expect(factory.count).toBe(1);
    client.dispose();
  });
});

describe("CG-G-01b a camera flood does not delay lease or telemetry", () => {
  it("delivers lease and telemetry before any camera frame, camera bounded", () => {
    const order: string[] = [];
    const { client, factory } = makeClient({
      onLeaseFrame: () => order.push("lease"),
      onTelemetry: () => order.push("telemetry"),
      onCamera: (frame) => order.push(`camera:${frame.slot}`),
    });
    client.start();
    const socket = factory.latest();

    for (let index = 0; index < 500; index += 1) {
      socket.receive(cameraRaw("left_wrist", "rgb", new Uint8Array([index & 0xff])));
    }
    socket.receive(textRaw(telemetryFrame(1)));
    socket.receive(
      textRaw(
        leaseGrantFrame({ sessionId: "s", generation: 1, sequence: 1, expiryMonoServer: 9, issuedMonoClient: 0 }),
      ),
    );

    client.pump();

    expect(order[0]).toBe("lease");
    expect(order[1]).toBe("telemetry");
    // The camera queue is bounded at 1: the flood cannot build a backlog.
    expect(order.filter((entry) => entry.startsWith("camera:"))).toHaveLength(1);
    client.dispose();
  });
});

describe("CG-G-01c bufferedAmount backpressure drops camera, protects the rest", () => {
  it("sheds camera frames over threshold while telemetry and lease are preserved", () => {
    const delivered: string[] = [];
    const { client, factory } = makeClient({
      onLeaseFrame: () => delivered.push("lease"),
      onTelemetry: () => delivered.push("telemetry"),
      onCamera: () => delivered.push("camera"),
    });
    client.start();
    const socket = factory.latest();
    socket.bufferedAmountValue = BUFFERED_AMOUNT_THRESHOLD_BYTES + 1;

    const cameraFloodCount = 20;
    for (let index = 0; index < cameraFloodCount; index += 1) {
      socket.receive(cameraRaw("left_wrist", "rgb", new Uint8Array([index])));
    }
    socket.receive(textRaw(telemetryFrame(1)));
    socket.receive(
      textRaw(
        leaseGrantFrame({ sessionId: "s", generation: 1, sequence: 1, expiryMonoServer: 9, issuedMonoClient: 0 }),
      ),
    );
    client.pump();

    expect(delivered).toContain("telemetry");
    expect(delivered).toContain("lease");
    expect(delivered).not.toContain("camera");
    expect(client.stats().backpressureDrops).toBe(cameraFloodCount);
    // The drop is counted against the camera stream, not the protected classes.
    expect(client.meter.stats(imageFeatureKey("left_wrist", "rgb")).dropCount).toBe(cameraFloodCount);
    client.dispose();
  });
});

describe("CG-G-01g an observer's control send is rejected server-side", () => {
  it("the frozen server rule refuses an observer control frame and admits an operator's", () => {
    // Server-side is authoritative: the FROZEN authorize_send rule rejects the
    // observer's send_action, independent of any client-side hiding.
    expect(fixtureServerAuthorize("observer", "command").accepted).toBe(false);
    expect(fixtureServerAuthorize("observer", "lease_renew").accepted).toBe(false);
    expect(fixtureServerAuthorize("operator", "command").accepted).toBe(true);
    // Observers may still receive read-only classes.
    expect(fixtureServerAuthorize("observer", "telemetry").accepted).toBe(true);
  });

  it("mirrors the refusal client-side as defence in depth", () => {
    const { client, factory } = makeClient({ role: "observer" });
    client.start();
    expect(() => client.send("command", { type: "command" })).toThrow(WsAuthorityError);
    // Nothing left the socket.
    expect(factory.latest().sent).toHaveLength(0);
    client.dispose();
  });

  it("blocks control sends after the observer-downgrade path", () => {
    const { client, factory } = makeClient({ role: "operator" });
    client.start();
    client.send("command", { type: "command", value: 1 });
    expect(factory.latest().sent).toHaveLength(1);

    client.downgradeToObserver();
    expect(() => client.send("command", { type: "command", value: 2 })).toThrow(WsAuthorityError);
    expect(factory.latest().sent).toHaveLength(1);
    client.dispose();
  });
});

describe("socket retry is WS-only and never re-attaches the backend Robot", () => {
  it("opens a fresh socket after a close without touching a second live channel", () => {
    const { client, factory, scheduler } = makeClient({ retryDelayMs: 1000 });
    client.start();
    expect(factory.count).toBe(1);

    factory.latest().emitClose();
    // Still one (or zero) live channel; the retry is a timer away.
    expect(client.stats().socketCount).toBe(0);

    scheduler.advance(1000);
    expect(factory.count).toBe(2);
    expect(client.stats().socketCount).toBe(1);
    expect(client.stats().socketGeneration).toBe(2);
    client.dispose();
  });

  it("counts a socket transport error without fabricating an OA-* envelope", () => {
    const onError = vi.fn();
    const { client, factory } = makeClient({ onError });
    client.start();
    factory.latest().emitError(new Error("boom"));
    expect(client.stats().socketErrorCount).toBe(1);
    expect(onError).not.toHaveBeenCalled();
    client.dispose();
  });
});

// A send that reaches no socket must never look like a send that worked. The stop is
// the case that makes this a safety property rather than a tidiness one: under
// CTR-WS@v2 `stop_hold` travels through WsClient.send, so a silent return would let
// an operator press STOP_HOLD against a closed socket and see nothing at all.
describe("a frame that reaches no socket is never silent", () => {
  it("throws on stop_hold with no socket, and counts it", () => {
    const { client } = makeClient({ role: "operator" });
    // Never started: there is no socket, which is the state a closed link leaves.
    expect(() => client.send("stop_hold", { type: "stop_hold", session_id: "s" })).toThrow(
      WsSendUndeliverableError,
    );
    expect(client.stats().undeliverableCount).toBe(1);
    client.dispose();
  });

  it("still signals the observer whose stop is the one FR-GUI-065 is written for", () => {
    // The observer passes authorization (stop_hold is not a control frame), so the
    // failure it must hear about is delivery, not authority. Asserting the error TYPE
    // is the point: a WsAuthorityError here would mean the stop was refused by role
    // and the reachability guarantee had quietly broken.
    const { client, factory } = makeClient({ role: "observer" });
    client.start();
    factory.latest().emitClose();

    let caught: unknown = null;
    try {
      client.send("stop_hold", { type: "stop_hold", session_id: "s" });
    } catch (error) {
      caught = error;
    }
    expect(caught).toBeInstanceOf(WsSendUndeliverableError);
    expect((caught as WsSendUndeliverableError).frameType).toBe("stop_hold");
    expect(client.stats().undeliverableCount).toBe(1);
    client.dispose();
  });

  it("counts a lost renewal without throwing, so the timer loop survives an outage", () => {
    // The one exemption. A renewal is emitted from setInterval with no caller to
    // catch anything, and a lost renewal is already expiry — the server holds the arm
    // when renewals stop. Throwing here would fire once per interval into the
    // scheduler for as long as the socket stayed down.
    const { client, factory, scheduler } = makeClient({
      role: "operator",
      renewIntervalMs: 250,
      retryDelayMs: 100_000,
    });
    client.start();
    const socket = factory.latest();
    socket.receive(
      textRaw(
        leaseGrantFrame({
          sessionId: "s",
          generation: 1,
          sequence: 1,
          expiryMonoServer: 9,
          issuedMonoClient: 0,
        }),
      ),
    );
    client.pump();
    socket.emitClose();

    // Several intervals with no socket: every tick is counted, none escapes.
    expect(() => scheduler.advance(1000)).not.toThrow();
    expect(client.stats().undeliverableCount).toBeGreaterThan(1);
    client.dispose();
  });

  it("throws on a re-arm confirm with no socket — an operator pressed it", () => {
    // rearm_confirm is client-authored like the renewal but is NOT exempt: a person
    // asked for the resume, so a dropped confirm must not leave them watching a
    // latched arm with no explanation.
    const { client, factory } = makeClient({ role: "operator" });
    client.start();
    const socket = factory.latest();
    socket.receive(textRaw(rearmIssueFrame("s", 2)));
    client.pump();
    socket.emitClose();

    expect(() => client.lease.confirmRearm()).toThrow(WsSendUndeliverableError);
    expect(client.stats().undeliverableCount).toBe(1);
    client.dispose();
  });

  it("does not confuse a saturated buffer with an absent socket", () => {
    // Backpressure is a different failure with a different answer: the transport is
    // there, so the frozen rule decides, and a protected frame is still sent.
    const { client, factory } = makeClient({ role: "operator" });
    client.start();
    factory.latest().bufferedAmountValue = BUFFERED_AMOUNT_THRESHOLD_BYTES + 1;

    expect(() => client.send("stop_hold", { type: "stop_hold", session_id: "s" })).not.toThrow();
    expect(factory.latest().sent).toHaveLength(1);
    expect(client.stats().undeliverableCount).toBe(0);
    client.dispose();
  });
});
