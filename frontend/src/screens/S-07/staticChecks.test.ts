// Static proofs the shipped S-07 source obeys the facade and safety rules:
//  - CG-G-S07a: the episode-control screen never wires a safety stop to the
//    recorder. It references NO global safety-stop symbol at all, and no recorder
//    command op is an E-Stop — so "E-Stop -> stop_recording" has zero wiring.
//  - Invariant I-2: no connect / disconnect / reconnect path and no WebSocket
//    construction (a browser reconnect would destroy zeroing).
//  - Facade: the screen re-sources nothing — it does not recompute the repo_id
//    stamp (CG-G-S07b) nor clamp/convert domain values.
// The scan reads the shipped modules only; *.test.* and the stylesheet are
// scaffolding and excluded. Comments are stripped first, so this header — which
// necessarily spells out the very words the scan forbids — is not itself a hit.

import { readFileSync, readdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));

const SHIPPED_FILES = readdirSync(HERE).filter(
  (name) => /\.(ts|tsx)$/.test(name) && !name.includes(".test."),
);

function shipped(file: string): string {
  return readFileSync(resolve(HERE, file), "utf-8");
}

// The code of a file with comments removed. The rules bind the code, not the prose
// that documents them.
function codeOf(file: string): string {
  return shipped(file)
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/.*$/gm, "");
}

describe("CG-G-S07a: episode control is never a safety stop", () => {
  // The WP-G-03 global safety-stop surface. The collect screen must not touch it —
  // if it holds no reference to it, it cannot wire it to the recorder.
  const SAFETY_STOP_SYMBOLS =
    /\bHARD_ESTOP\b|\bSOFT_STOP\b|\bSTOP_KINDS\b|\bStopControls\b|\bstopControls\b|HARD_ESTOP_DROP_WARNING/;

  it("no shipped file references any global safety-stop symbol", () => {
    for (const file of SHIPPED_FILES) {
      expect(codeOf(file), `${file} must not reference a safety-stop symbol`).not.toMatch(
        SAFETY_STOP_SYMBOLS,
      );
    }
  });

  it("no shipped file imports from the global stopControls module", () => {
    for (const file of SHIPPED_FILES) {
      expect(codeOf(file)).not.toMatch(/from\s+["'][^"']*stopControls["']/);
    }
  });

  it("no recorder command op is an E-Stop, and session_stop exists (non-vacuous)", () => {
    const ops = [...codeOf("commands.ts").matchAll(/\bop:\s*"([^"]+)"/g)].map((m) => m[1]);
    expect(ops.length).toBeGreaterThan(0);
    expect(ops).toContain("session_stop");
    for (const op of ops) {
      expect(op, `op ${op} must not be an E-Stop`).not.toMatch(/e[-_ ]?stop/i);
    }
  });
});

describe("invariant I-2: no reconnect path, no socket construction", () => {
  it("no shipped file references connect / disconnect / reconnect", () => {
    const forbidden = /\b(reconnect|disconnect)\b|\bconnect\s*\(|재연결/;
    for (const file of SHIPPED_FILES) {
      expect(codeOf(file), `${file} must hold no reconnect path`).not.toMatch(forbidden);
    }
  });

  it("no shipped file constructs a WebSocket", () => {
    for (const file of SHIPPED_FILES) {
      expect(codeOf(file), `${file} must not open a socket`).not.toMatch(
        /new\s+WebSocket\b|\bWebSocket\b/,
      );
    }
  });
});

describe("facade: S-07 re-sources nothing", () => {
  it("does not recompute the repo_id stamp (CG-G-S07b renders the backend field)", () => {
    for (const file of SHIPPED_FILES) {
      expect(codeOf(file), `${file} must not build a repo_id stamp`).not.toMatch(
        /stamp_repo_id\s*\(|strftime|toISOString|Date\.now\s*\(|new\s+Date\s*\(/,
      );
    }
  });

  it("does no browser-side clamp or deg<->rad conversion", () => {
    for (const file of SHIPPED_FILES) {
      expect(codeOf(file), `${file} must not clamp or convert domain values`).not.toMatch(
        /\bclamp\b|Math\.PI|deg2rad|rad2deg/i,
      );
    }
  });
});
