// The server's refusal close codes, mirrored for the browser.
//
// These are NOT part of CTR-WS@v2. The contract declares ten frame types and no
// server-to-client error frame (`contracts/ws/schema.py` FRAME_TABLE), so a refusal has
// no envelope to travel in and the backend answers it with a WebSocket close instead —
// `backend/ws/constants.py` owns the codes and says so. That module is the canon; this
// file mirrors it and `closeCodes.contract.test.ts` reads the Python to keep the two
// from drifting.
//
// Two distinctions, not one, and the second is the load-bearing one:
//
//   1. A close carrying one of these codes is a refusal, not transport. Counting them
//      apart from a dropped link is what makes a reconnect loop measurable.
//   2. Among the refusals, only three are verdicts on the CONNECTION. The rest are
//      verdicts on ONE FRAME the client chose to send, and a fresh socket that does not
//      send that frame is accepted.
//
// Retry is derived per refusal from what the socket carries, not from a house rule.
// This channel carries the GUI soft stop, and `FR-GUI-065` puts that within reach of
// every role — `backend/ws/arm_channel.py` states it directly for the read-only host
// that answers `command` with 4408: "a deployment with no send path still answers
// FR-GUI-065". So tearing the channel down for the life of the page is the worse
// outcome wherever a reconnect could work, and only the handshake codes are the case
// where it provably cannot: the URL, the role and the origin are fixed when the client
// is constructed, so the next socket earns the identical verdict before it reads a byte.
//
// What retrying the per-frame refusals costs: a client whose bug reproduces on every
// socket — a role the server and the browser disagree about, say — reconnects once per
// retry delay for as long as the page is open. That loop is not silent; it is what
// `refusalCount` counts.

// RFC 6455 §7.4.2 private range. The backend allocates its refusals from the bottom of
// it; the bound is what keeps a future code from being read as transport by default.
export const REFUSAL_CODE_MIN = 4400;
export const REFUSAL_CODE_MAX = 4499;

// One per refusal, mirroring `backend/ws/constants.py`. Named rather than kept as a bare
// range so a reader can see which refusals exist without opening the Python.
export const WS_CLOSE_UNKNOWN_ROLE = 4400;
export const WS_CLOSE_MISSING_SESSION = 4401;
export const WS_CLOSE_MALFORMED_FRAME = 4402;
export const WS_CLOSE_UNKNOWN_FRAME_TYPE = 4403;
export const WS_CLOSE_UNAUTHORIZED_FRAME = 4404;
export const WS_CLOSE_WRONG_DIRECTION = 4405;
export const WS_CLOSE_REARM_NOT_ISSUED = 4406;
export const WS_CLOSE_FORBIDDEN_ORIGIN = 4407;
export const WS_CLOSE_COMMAND_UNROUTABLE = 4408;

// The three the handshake decides, before any frame is read
// (`backend/ws/app.py` `handshake_session`). Each is settled by the URL and the Origin
// header, both fixed for the life of this client, so every retry earns the same close.
export const HANDSHAKE_REFUSAL_CODES: readonly number[] = [
  WS_CLOSE_UNKNOWN_ROLE,
  WS_CLOSE_MISSING_SESSION,
  WS_CLOSE_FORBIDDEN_ORIGIN,
];

export const SERVER_REFUSAL_CODES: readonly number[] = [
  WS_CLOSE_UNKNOWN_ROLE,
  WS_CLOSE_MISSING_SESSION,
  WS_CLOSE_MALFORMED_FRAME,
  WS_CLOSE_UNKNOWN_FRAME_TYPE,
  WS_CLOSE_UNAUTHORIZED_FRAME,
  WS_CLOSE_WRONG_DIRECTION,
  WS_CLOSE_REARM_NOT_ISSUED,
  WS_CLOSE_FORBIDDEN_ORIGIN,
  WS_CLOSE_COMMAND_UNROUTABLE,
];

// One refusal, as the browser received it. The reason is the server's own words, already
// cut to RFC 6455's 123-byte close payload by `truncate_close_reason` on the backend.
// The browser neither authors nor translates it: a refusal restated by the client is a
// refusal the operator cannot match against a server log.
export interface LinkRefusal {
  code: number;
  reason: string;
}

// Whether this close code is a refusal rather than transport. The test is the range, not
// the enumerated list, so a code the backend adds tomorrow is still counted as a refusal
// rather than disappearing into the transport tally.
export function isServerRefusal(code: number): boolean {
  return code >= REFUSAL_CODE_MIN && code <= REFUSAL_CODE_MAX;
}

// Whether reconnecting is pointless. Enumerated rather than ranged, and that asymmetry
// with `isServerRefusal` is deliberate: an unrecognised code defaults to retrying, which
// keeps the soft stop reachable. Defaulting the other way would let one new backend code
// silently take the stop away from every page that hits it.
export function isHandshakeRefusal(code: number): boolean {
  return HANDSHAKE_REFUSAL_CODES.includes(code);
}
