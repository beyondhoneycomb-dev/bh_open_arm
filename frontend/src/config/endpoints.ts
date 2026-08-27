// Same-origin backend surface. Every path here is relative: the SPA, the REST
// API and the single WebSocket are all served by the one FastAPI backend on the
// SPA-serving port (13 §2.7, default :8000), so the browser never names an
// external origin. The WS scheme (wss vs ws) and absolute URL are derived from
// `location` by the WS client (WP-G-01) — the shell only fixes the paths.

// The one realtime channel (CTR-WS@v2, D-2). Exactly one WebSocket multiplexes
// telemetry + command + camera + soft stop + lease; the shell exposes only its path.
//
// It must equal `REALTIME_ROUTE` in backend/ws/constants.py, which is where the server mounts
// the route. The two are written in different languages and there is no shared source for them,
// so the equality is checked by a test that reads this file
// (`tests/wpg00_backend/test_serve.py`) — a mismatch here is a handshake that never happens,
// and it surfaces to the operator as a connection error, which reads like a backend that is down.
export const WS_ENDPOINT_PATH = "/ws/realtime";

// REST (CRUD, non-realtime). Config canon is the backend runtime_config.json;
// the browser does REST get/set against this endpoint only.
export const CONFIG_ENDPOINT = "/api/config";

// The end-effector tools the backend registry has (read-only). The registry is
// open — tools are added there, not here — so the browser asks for the choices
// instead of carrying a list that would go stale the day a tool is registered.
export const CONFIG_TOOLS_ENDPOINT = `${CONFIG_ENDPOINT}/tools`;

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

// The camera device panel's surface (S-06, `06` FR-CAM-004). Which physical camera fills which
// slot is the operator's answer, given here against a live preview, and the backend persists it.
//
// These must equal `CAMERA_*_ROUTE` in backend/config/constants.py — same split-brain as
// `WS_ENDPOINT_PATH` above, checked by the same kind of contract test.
export const CAMERA_DEVICES_ENDPOINT = "/api/cameras/devices";

// The slot to assign or clear. `slot` is a registered slot key from the scan.
export function cameraSlotEndpoint(slot: string): string {
  return `/api/cameras/slots/${encodeURIComponent(slot)}`;
}

// One JPEG frame from the camera on a port. A still rather than a stream: the slot's real stream
// belongs to the capture run, and a second reader on the same node takes frames that run counts.
export function cameraPreviewEndpoint(portPath: string): string {
  return `${CAMERA_DEVICES_ENDPOINT}/${encodeURIComponent(portPath)}/preview`;
}
