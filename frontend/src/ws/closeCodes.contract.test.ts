// The mirror proof for the refusal close codes. `backend/ws/constants.py` owns them —
// they are transport, not CTR-WS@v2 — so this test reads that module and asserts the
// browser mirror names the same codes with the same numbers. A backend that adds,
// renumbers or removes a refusal fails here rather than leaving the browser to read the
// new code as a retryable transport close.

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { repoFile } from "../global/testSupport/repoRoot";
import {
  HANDSHAKE_REFUSAL_CODES,
  isHandshakeRefusal,
  isServerRefusal,
  REFUSAL_CODE_MAX,
  REFUSAL_CODE_MIN,
  SERVER_REFUSAL_CODES,
  WS_CLOSE_COMMAND_UNROUTABLE,
  WS_CLOSE_FORBIDDEN_ORIGIN,
  WS_CLOSE_UNAUTHORIZED_FRAME,
} from "./closeCodes";

const constantsText = readFileSync(repoFile("backend/ws/constants.py"), "utf-8");
const appText = readFileSync(repoFile("backend/ws/app.py"), "utf-8");

// The payload limit is the one WS_CLOSE_* name in that module that is not a close code.
const NOT_A_CLOSE_CODE = "WS_CLOSE_REASON_MAX_BYTES";

// Every WS_CLOSE_* name the module exports, read from `__all__`. This is the count the
// assignment scan is checked against: a regex that quietly matches fewer names than the
// module exports would let a new backend code ship unmirrored with a green test, which is
// the same silence this whole module exists to remove.
function exportedCloseNames(): string[] {
  const allBlock = /__all__ = \[([\s\S]*?)\]/.exec(constantsText);
  if (allBlock === null) {
    throw new Error("backend/ws/constants.py has no __all__ block to cross-check against");
  }
  return [...allBlock[1].matchAll(/"(WS_CLOSE_[A-Z_]+)"/g)]
    .map((match) => match[1])
    .filter((name) => name !== NOT_A_CLOSE_CODE);
}

// Assignments only, and tolerant of a trailing comment or a type annotation — a name that
// grew either would otherwise vanish from this map without failing anything. The `__all__`
// block repeats every name as a string, so the anchors keep it from being counted twice.
function backendCloseCodes(): Map<string, number> {
  const found = new Map<string, number>();
  const pattern = /^(WS_CLOSE_[A-Z_]+)(?::\s*[A-Za-z_[\]. ]+)? = (\d+)\s*(?:#.*)?$/gm;
  let match = pattern.exec(constantsText);
  while (match !== null) {
    if (match[1] !== NOT_A_CLOSE_CODE) {
      found.set(match[1], Number(match[2]));
    }
    match = pattern.exec(constantsText);
  }
  return found;
}

// The codes `handshake_session` itself returns — the refusals decided before a frame is
// read. Parsed from the function body rather than restated, because the whole point of the
// handshake set is that it tracks what that function does.
function handshakeCloseNames(): string[] {
  const start = appText.indexOf("def handshake_session(");
  const end = appText.indexOf("\ndef ", start + 1);
  if (start < 0 || end < 0) {
    throw new Error("could not isolate handshake_session in backend/ws/app.py");
  }
  const body = appText.slice(start, end);
  return [...new Set([...body.matchAll(/code=(WS_CLOSE_[A-Z_]+)/g)].map((match) => match[1]))];
}

describe("the browser mirrors the backend's refusal close codes", () => {
  it("reads every close code the backend module exports", () => {
    // Guards the scan itself. Without this the regex can silently match fewer names than
    // exist and every assertion below still passes on a shrunken map.
    expect([...backendCloseCodes().keys()].sort()).toEqual(exportedCloseNames().sort());
  });

  it("names every refusal code the backend defines, with the same number", () => {
    const backend = backendCloseCodes();
    expect(backend.size).toBeGreaterThan(0);

    const backendCodes = [...backend.values()].sort((a, b) => a - b);
    expect([...SERVER_REFUSAL_CODES].sort((a, b) => a - b)).toEqual(backendCodes);
  });

  it("keeps every backend refusal inside the range the client classifies by", () => {
    const backend = backendCloseCodes();
    for (const [name, code] of backend) {
      expect(code, `${name} sits outside the refusal range`).toBeGreaterThanOrEqual(
        REFUSAL_CODE_MIN,
      );
      expect(code, `${name} sits outside the refusal range`).toBeLessThanOrEqual(
        REFUSAL_CODE_MAX,
      );
    }
  });
});

describe("the handshake set tracks what handshake_session actually refuses", () => {
  it("holds exactly the codes that function returns, and no others", () => {
    const backend = backendCloseCodes();
    const expected = handshakeCloseNames()
      .map((name) => backend.get(name))
      .sort((a, b) => (a ?? 0) - (b ?? 0));
    expect(expected).not.toContain(undefined);
    expect([...HANDSHAKE_REFUSAL_CODES].sort((a, b) => a - b)).toEqual(expected);
  });

  it("classifies a per-frame refusal as retryable", () => {
    // The soft stop rides this socket. A refusal decided on one frame must not end the
    // channel, or `FR-GUI-065` stops holding after the first refused command.
    expect(isHandshakeRefusal(WS_CLOSE_COMMAND_UNROUTABLE)).toBe(false);
    expect(isHandshakeRefusal(WS_CLOSE_UNAUTHORIZED_FRAME)).toBe(false);
    expect(isHandshakeRefusal(WS_CLOSE_FORBIDDEN_ORIGIN)).toBe(true);
  });

  it("defaults an unallocated code to retryable", () => {
    expect(isHandshakeRefusal(REFUSAL_CODE_MAX)).toBe(false);
    expect(isServerRefusal(REFUSAL_CODE_MAX)).toBe(true);
  });
});

describe("isServerRefusal separates a refusal from transport", () => {
  it("calls the backend's own codes refusals", () => {
    expect(isServerRefusal(WS_CLOSE_UNAUTHORIZED_FRAME)).toBe(true);
    expect(isServerRefusal(WS_CLOSE_FORBIDDEN_ORIGIN)).toBe(true);
    expect(isServerRefusal(WS_CLOSE_COMMAND_UNROUTABLE)).toBe(true);
  });

  it("calls a normal and an abnormal transport close transport", () => {
    // 1000 is a clean close, 1006 is the code the browser synthesises when the link
    // dropped with no close frame at all — the case the retry exists for.
    expect(isServerRefusal(1000)).toBe(false);
    expect(isServerRefusal(1006)).toBe(false);
  });

  it("covers a code the backend has not allocated yet", () => {
    expect(isServerRefusal(REFUSAL_CODE_MAX)).toBe(true);
    expect(isServerRefusal(REFUSAL_CODE_MIN - 1)).toBe(false);
    expect(isServerRefusal(REFUSAL_CODE_MAX + 1)).toBe(false);
  });
});
