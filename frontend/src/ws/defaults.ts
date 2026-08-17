// Production wiring for the one WS client: the browser WebSocket + the real
// decode worker, at the same-origin realtime path (the single realtime channel,
// D-2). App screens call this; the vitest lane never imports the client factory, so the Worker
// global and its bundle transform stay out of the test import graph — which is why the URL
// derivation is a separate export the lane can reach on its own.

import { WS_ENDPOINT_PATH } from "../config/endpoints";
import { createBrowserDecoderPort } from "./browserDecoderPort";
import { newSessionId, realtimeUrl } from "./handshakeUrl";
import { systemScheduler } from "./types";
import { browserWebSocketFactory, WsClient, type WsClientOptions } from "./wsClient";

export type WsClientOverrides = Partial<Omit<WsClientOptions, "socketFactory" | "decoderPort">> & {
  // This connection's identifier. Omitted, a fresh one is minted — one per client, so two tabs
  // are two sessions and the server can say which of them sent a soft stop.
  sessionId?: string;
};

// The role a page holds until something asks for another one. Observer is the least authority a
// connection can carry: it reads, and the server refuses every control frame it sends except the
// soft stop. Defaulting to operator would take the single control lease merely by loading the
// page.
const DEFAULT_ROLE = "observer";

// Derive the URL the client connects on, with both parameters the handshake requires. Separate
// from `createDefaultWsClient` so it can be exercised without pulling in a real Worker.
export function defaultWsUrl(
  location: { protocol: string; host: string },
  identity: { role?: string; sessionId?: string },
): string {
  return realtimeUrl(location, WS_ENDPOINT_PATH, {
    role: identity.role ?? DEFAULT_ROLE,
    sessionId: identity.sessionId ?? newSessionId(),
  });
}

export function createDefaultWsClient(overrides: WsClientOverrides = {}): WsClient {
  const { sessionId, ...clientOverrides } = overrides;
  const url =
    clientOverrides.url ??
    defaultWsUrl(window.location, { role: clientOverrides.role, sessionId });
  return new WsClient({
    scheduler: systemScheduler,
    ...clientOverrides,
    url,
    socketFactory: browserWebSocketFactory,
    decoderPort: createBrowserDecoderPort(),
  });
}
