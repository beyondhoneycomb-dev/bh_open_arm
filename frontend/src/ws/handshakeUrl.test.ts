// The realtime URL must carry what the server's handshake refuses to proceed without.
//
// `backend/ws/app.py` reads `role` and `session_id` off the query string BEFORE it will accept
// a connection, and answers a missing one with a close: 4400 for an unknown role and 4401 for a
// missing session. The refusal lands AFTER `accept()`, so a client that omits them opens a
// socket, receives a close, and looks to the operator exactly like a backend that is down.
//
// The session id is what the server attributes a soft stop to — the latch reason it records is
// `gui-stop:<session_id>` — so it is not decoration, it is the audit's only handle on which of
// the operator's tabs pressed the button.

import { describe, expect, it } from "vitest";

import { REALTIME_ROLE_PARAM, REALTIME_SESSION_PARAM, newSessionId, realtimeUrl } from "./handshakeUrl";
import { WS_ENDPOINT_PATH } from "../config/endpoints";

const LOOPBACK = { protocol: "http:", host: "127.0.0.1:8000" };
const TLS = { protocol: "https:", host: "arm.local" };

describe("realtimeUrl", () => {
  it("carries the role and the session id the handshake requires", () => {
    const url = new URL(
      realtimeUrl(LOOPBACK, WS_ENDPOINT_PATH, { role: "observer", sessionId: "s-1" }),
    );

    expect(url.searchParams.get(REALTIME_ROLE_PARAM)).toBe("observer");
    expect(url.searchParams.get(REALTIME_SESSION_PARAM)).toBe("s-1");
  });

  it("keeps the path the server mounts the route on", () => {
    const url = new URL(
      realtimeUrl(LOOPBACK, WS_ENDPOINT_PATH, { role: "observer", sessionId: "s-1" }),
    );

    expect(url.pathname).toBe(WS_ENDPOINT_PATH);
  });

  it("stays same-origin and follows the page scheme", () => {
    // The air gap forbids naming an external origin, and a page served over TLS may not open a
    // plaintext socket — the browser blocks it as mixed content.
    expect(realtimeUrl(LOOPBACK, WS_ENDPOINT_PATH, { role: "observer", sessionId: "s" })).toMatch(
      /^ws:\/\/127\.0\.0\.1:8000\//,
    );
    expect(realtimeUrl(TLS, WS_ENDPOINT_PATH, { role: "observer", sessionId: "s" })).toMatch(
      /^wss:\/\/arm\.local\//,
    );
  });

  it("escapes a session id that would otherwise change the query", () => {
    // The id reaches the server as an identifier and comes back in a latch reason. One that
    // smuggled an `&` would arrive truncated and attribute a stop to a session nobody opened.
    const url = new URL(
      realtimeUrl(LOOPBACK, WS_ENDPOINT_PATH, { role: "operator", sessionId: "a&role=admin" }),
    );

    expect(url.searchParams.get(REALTIME_SESSION_PARAM)).toBe("a&role=admin");
    expect(url.searchParams.get(REALTIME_ROLE_PARAM)).toBe("operator");
  });

  it("refuses an empty session id rather than opening a socket that will be closed", () => {
    // 4401 arrives after accept, so the operator sees a socket that opened and then dropped.
    // Refusing here names the cause while there is still a caller to name it to.
    expect(() =>
      realtimeUrl(LOOPBACK, WS_ENDPOINT_PATH, { role: "observer", sessionId: "" }),
    ).toThrow(/session/i);
  });
});

describe("newSessionId", () => {
  it("produces a non-empty id", () => {
    expect(newSessionId().length).toBeGreaterThan(0);
  });

  it("produces a different id each time", () => {
    // Two tabs must not share one id: the server attributes a stop to the session that sent it,
    // and two tabs under one id make the audit unable to say which operator acted.
    const ids = new Set(Array.from({ length: 32 }, () => newSessionId()));

    expect(ids.size).toBe(32);
  });
});

describe("the shell's WS path matches the route the server mounts", () => {
  it("names /ws/realtime", () => {
    // Spelled out here rather than compared to itself. The backend's REALTIME_ROUTE is the other
    // half of this pair and `tests/wpg00_backend/test_serve.py` holds it to the same string; a
    // mismatch is a handshake that never happens and surfaces as a connection error.
    expect(WS_ENDPOINT_PATH).toBe("/ws/realtime");
  });
});
