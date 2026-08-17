// The realtime URL, carrying what the server refuses to proceed without.
//
// `backend/ws/app.py`'s handshake reads `role` and `session_id` off the query string before it
// will serve a connection, and answers a missing one with a close — 4400 for an unrecognised
// role, 4401 for a missing session. Both land AFTER `accept()`, on purpose, so the browser gets
// a code it can read instead of a bare HTTP 403; the cost is that a client which omits them
// opens a socket, is closed, and presents to the operator exactly like a backend that is down.
//
// The session id is not decoration. The server attributes a soft stop to it — the latch reason
// it records is `gui-stop:<session_id>` — so it is the audit's only handle on which of the
// operator's open tabs pressed the button. Two tabs sharing one id make that unanswerable.
//
// The two parameter names are spelled here rather than imported from the backend for the obvious
// reason that they are in another language; `tests/wpg00_backend/test_serve.py` is the pattern
// this project uses for keeping a cross-language constant honest, and the same is owed here.

// The query parameters `backend/ws/constants.py` names ROLE_QUERY_PARAM and SESSION_QUERY_PARAM.
export const REALTIME_ROLE_PARAM = "role";
export const REALTIME_SESSION_PARAM = "session_id";

const WS_PLAINTEXT = "ws";
const WS_SECURE = "wss";
const HTTPS_PROTOCOL = "https:";

export interface HandshakeIdentity {
  // The CTR-WS@v2 role this connection claims. The server judges every frame against it and
  // never re-negotiates it on a live socket, so a client wanting another role opens another
  // connection.
  role: string;
  // This connection's identifier, unique per tab.
  sessionId: string;
}

export class HandshakeIdentityError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "HandshakeIdentityError";
  }
}

// Build the same-origin realtime URL. Same-origin only: the air gap forbids naming an external
// origin, and the scheme follows the page because a TLS page may not open a plaintext socket —
// the browser blocks that as mixed content before the server ever sees it.
export function realtimeUrl(
  location: { protocol: string; host: string },
  path: string,
  identity: HandshakeIdentity,
): string {
  if (!identity.sessionId) {
    throw new HandshakeIdentityError(
      "a realtime connection needs a session_id; the server closes one without it (4401) " +
        "after accepting the socket, which reads as a backend that is down",
    );
  }
  if (!identity.role) {
    throw new HandshakeIdentityError(
      "a realtime connection needs a role; the server closes an unrecognised one (4400) and " +
        "will not guess a least-privileged default, because that would hand an unnamed " +
        "connection the soft stop under an identity nobody assigned",
    );
  }
  const scheme = location.protocol === HTTPS_PROTOCOL ? WS_SECURE : WS_PLAINTEXT;
  // Built through URLSearchParams rather than by concatenation: an id carrying an `&` would
  // otherwise arrive truncated, and the server would attribute a stop to a session that never
  // opened.
  const query = new URLSearchParams({
    [REALTIME_ROLE_PARAM]: identity.role,
    [REALTIME_SESSION_PARAM]: identity.sessionId,
  });
  return `${scheme}://${location.host}${path}?${query.toString()}`;
}

// A fresh identifier for this tab's connection. `crypto.randomUUID` is available in every
// browser this SPA targets and in the test environment; there is no fallback, because an id
// generator that quietly degraded to something guessable would produce collisions between tabs
// and the audit would then name the wrong session.
export function newSessionId(): string {
  return crypto.randomUUID();
}
