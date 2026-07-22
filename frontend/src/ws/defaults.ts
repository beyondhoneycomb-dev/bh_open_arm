// Production wiring for the one WS client: the browser WebSocket + the real
// decode worker, at the same-origin `/ws` path (the single realtime channel,
// D-2). App screens call this; the vitest lane never imports it, so the Worker
// global and its bundle transform stay out of the test import graph.

import { WS_ENDPOINT_PATH } from "../config/endpoints";
import { createBrowserDecoderPort } from "./browserDecoderPort";
import { systemScheduler } from "./types";
import {
  browserWebSocketFactory,
  resolveWsUrl,
  WsClient,
  type WsClientOptions,
} from "./wsClient";

export type WsClientOverrides = Partial<Omit<WsClientOptions, "socketFactory" | "decoderPort">>;

export function createDefaultWsClient(overrides: WsClientOverrides = {}): WsClient {
  const url = overrides.url ?? resolveWsUrl(window.location, WS_ENDPOINT_PATH);
  return new WsClient({
    scheduler: systemScheduler,
    ...overrides,
    url,
    socketFactory: browserWebSocketFactory,
    decoderPort: createBrowserDecoderPort(),
  });
}
