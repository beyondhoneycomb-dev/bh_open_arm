// CG-G-04a and CG-G-04e as static scans over the production source set. A mode
// change is the movement of send_action authority, never a Robot connect()/
// disconnect() — connect() calls set_zero_position() and silently invalidates
// zeroing (I-2, FR-GUI-081). And no GUI path may spawn an external CAN client;
// that is permitted only in MOTOR_SETUP, and never from browser code (FR-GUI-086).
// This scans src (minus test files) plus index.html: comments explain these
// invariants by naming the forbidden symbols and are stripped before scanning,
// exactly as the WP-G-00 air-gap scan does, because Vite drops them from the bundle.

import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const FRONTEND_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");

const SCANNED_EXTENSIONS: ReadonlySet<string> = new Set([".ts", ".tsx", ".html"]);

// A Robot session opens exactly once; connect()/disconnect() as a call symbol is
// forbidden GUI-wide, and so is the "reconnect" label (there is no reconnect
// button — the browser only retries the WS, never the backend Robot).
const CONNECT_CALL = /\b(?:dis)?connect\s*\(/;
const RECONNECT_LABEL = /reconnect/i;

// External CAN clients the GUI must never expose a spawn path for (CG-G-04e).
const CAN_CLIENT_TOKENS = ["openarm-can-cli", "openarm_teleop", "openarm-teleop", "cansend"];

function isTestFile(path: string): boolean {
  return /\.test\.(ts|tsx)$/.test(path) || path.endsWith("test-setup.ts");
}

// Strip comments before scanning: the forbidden symbols appear in comments that
// document the invariants, and Vite removes comments from the bundle, so a symbol
// inside a comment is neither a call nor a shipped label. The `://` guard keeps a
// URL inside a code string from being read as a line comment.
function stripComments(path: string, text: string): string {
  let out = text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/<!--[\s\S]*?-->/g, "");
  if (/\.(ts|tsx|js|mjs)$/.test(path)) {
    out = out.replace(/(?<!:)\/\/.*$/gm, "");
  }
  return out;
}

function collectFiles(dir: string, acc: string[]): string[] {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === "dist") {
      continue;
    }
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      collectFiles(full, acc);
    } else if (SCANNED_EXTENSIONS.has(extname(full)) && !isTestFile(full)) {
      acc.push(full);
    }
  }
  return acc;
}

function productionSources(): string[] {
  const files = [join(FRONTEND_ROOT, "index.html")];
  collectFiles(join(FRONTEND_ROOT, "src"), files);
  return files;
}

describe("CG-G-04a no connect()/disconnect()/reconnect in GUI code", () => {
  it("names no Robot connect()/disconnect() call symbol", () => {
    const offenders: string[] = [];
    for (const file of productionSources()) {
      const text = stripComments(file, readFileSync(file, "utf-8"));
      if (CONNECT_CALL.test(text)) {
        offenders.push(file);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("carries no reconnect label", () => {
    const offenders: string[] = [];
    for (const file of productionSources()) {
      const text = stripComments(file, readFileSync(file, "utf-8"));
      if (RECONNECT_LABEL.test(text)) {
        offenders.push(file);
      }
    }
    expect(offenders).toEqual([]);
  });
});

describe("CG-G-04e no external CAN-client spawn path in GUI code", () => {
  it("references no external CAN client executable", () => {
    const offenders: string[] = [];
    for (const file of productionSources()) {
      const text = stripComments(file, readFileSync(file, "utf-8"));
      for (const token of CAN_CLIENT_TOKENS) {
        if (text.includes(token)) {
          offenders.push(`${file}: ${token}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
