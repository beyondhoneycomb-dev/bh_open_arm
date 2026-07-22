// Same-origin backend surface. Every path here is relative: the SPA, the REST
// API and the single WebSocket are all served by the one FastAPI backend on the
// SPA-serving port (13 §2.7, default :8000), so the browser never names an
// external origin. The WS scheme (wss vs ws) and absolute URL are derived from
// `location` by the WS client (WP-G-01) — the shell only fixes the paths.

// The one realtime channel (CTR-WS@v1, D-2). Exactly one WebSocket multiplexes
// telemetry + command + camera + lease; the shell exposes only its path.
export const WS_ENDPOINT_PATH = "/ws";

// REST (CRUD, non-realtime). Config canon is the backend runtime_config.json;
// the browser does REST get/set against this endpoint only.
export const CONFIG_ENDPOINT = "/api/config";

// Per-screen domain-spec lookup (CG-G-00c): each screen resolves which domain
// specification document it is the window onto, addressable under this base.
export const SPEC_ENDPOINT_BASE = "/api/spec";

// Backend default port (13 §2.7, M8). Configurable server-side; the browser uses
// same-origin relative URLs and never this literal at runtime.
export const DEFAULT_BACKEND_PORT = 8000;

// Dev-server proxy targets only. localhost is the backend on this machine, not
// an external origin — the air-gap scan (CG-G-00a) treats localhost/127.0.0.1 as
// same-machine. These literals never enter the built bundle.
export const REST_DEV_PROXY_TARGET = `http://localhost:${DEFAULT_BACKEND_PORT}`;
export const WS_DEV_PROXY_TARGET = `http://localhost:${DEFAULT_BACKEND_PORT}`;
