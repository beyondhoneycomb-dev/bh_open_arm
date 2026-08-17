// The production factory must build a URL the server will actually serve.
//
// `createDefaultWsClient` is what the shell calls, and until it carried a role and a session id
// every connection it made was accepted and then closed — 4400 or 4401 — which is
// indistinguishable at the browser from a backend that is down.
//
// Only the URL is exercised here. Constructing the client itself pulls in the real decode Worker
// and the browser WebSocket, neither of which belongs in this lane; `defaults.ts` keeps the URL
// derivation separable for exactly that reason.

import { describe, expect, it } from "vitest";

import { WS_ENDPOINT_PATH } from "../config/endpoints";
import { defaultWsUrl } from "./defaults";
import { REALTIME_ROLE_PARAM, REALTIME_SESSION_PARAM } from "./handshakeUrl";

const LOOPBACK = { protocol: "http:", host: "127.0.0.1:8000" };

describe("defaultWsUrl", () => {
  it("carries both handshake parameters", () => {
    const url = new URL(defaultWsUrl(LOOPBACK, { role: "observer", sessionId: "s-1" }));

    expect(url.pathname).toBe(WS_ENDPOINT_PATH);
    expect(url.searchParams.get(REALTIME_ROLE_PARAM)).toBe("observer");
    expect(url.searchParams.get(REALTIME_SESSION_PARAM)).toBe("s-1");
  });

  it("opens as an observer when no role is named", () => {
    // The least authority a connection can hold. An operator connection takes the single control
    // lease, so a shell that defaulted to it would take control merely by loading the page —
    // and `WsClient` already treats observer as its own default role for the same reason.
    const url = new URL(defaultWsUrl(LOOPBACK, { sessionId: "s-1" }));

    expect(url.searchParams.get(REALTIME_ROLE_PARAM)).toBe("observer");
  });

  it("mints a session id when none is supplied", () => {
    const first = new URL(defaultWsUrl(LOOPBACK, {}));
    const second = new URL(defaultWsUrl(LOOPBACK, {}));

    const a = first.searchParams.get(REALTIME_SESSION_PARAM);
    const b = second.searchParams.get(REALTIME_SESSION_PARAM);
    expect(a).toBeTruthy();
    expect(a).not.toBe(b);
  });
});
