// Static proofs the shipped S-01 source obeys the aggregation-facade invariants a
// render test cannot prove absent. They scan the shipped .ts/.tsx modules only
// (*.test.* excluded). Comments are stripped first, so these headers — which spell
// out the very tokens the scans forbid — are never themselves hits.
//
//   - CG-G-S01a: the dashboard computes no metric and decides no threshold. There
//     is no Math.*, no number formatting, no numeric coercion, no comparison
//     against a number, and no arithmetic on values anywhere in the shipped code.
//     The one presence check the design REQUIRES (not-landed -> UNAVAILABLE) is a
//     `??`, not a threshold. String literals are stripped for this scan so a
//     backend-formatted display string ("3.1 / 16.0 GB") is data, not arithmetic.
//   - CG-G-S01c: no hardcoded camera-tile-count constant; the tile set is the
//     length of the active-stream array.
//   - CG-G-S01d: the cycle-time source is the PG-RT-001b artifact and only that —
//     no reference to the provisional PG-RT-001a, and the colliding spec token
//     (15's cycle-time vs 16's Quest-accuracy 'M-8') appears nowhere.
//   - facade / I-2: no socket, no reconnect, no browser wall-clock, no external
//     origin.

import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, extname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const SCREEN_ROOT = dirname(fileURLToPath(import.meta.url));
const SCANNED_EXTENSIONS: ReadonlySet<string> = new Set([".ts", ".tsx"]);

function isTestFile(path: string): boolean {
  return /\.test\.(ts|tsx)$/.test(path);
}

function collectSources(dir: string, acc: string[]): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      collectSources(full, acc);
    } else if (SCANNED_EXTENSIONS.has(extname(full)) && !isTestFile(full)) {
      acc.push(full);
    }
  }
  return acc;
}

// Code with comments removed. The `:` guard keeps `https://`-style tokens intact
// so the external-origin scan still sees them.
function stripComments(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(?<!:)\/\/.*$/gm, "");
}

// Code with comments AND quoted string literals removed. Used only for the
// no-computation scan, so a backend-formatted display string is not mistaken for
// arithmetic. Template literals are kept, so arithmetic hidden in `${...}` would
// still be caught.
function stripCommentsAndStrings(text: string): string {
  return stripComments(text)
    .replace(/"(?:[^"\\]|\\.)*"/g, '""')
    .replace(/'(?:[^'\\]|\\.)*'/g, "''");
}

const SOURCES = collectSources(SCREEN_ROOT, []).map((path) => ({
  path,
  code: stripComments(readFileSync(path, "utf-8")),
  computeCode: stripCommentsAndStrings(readFileSync(path, "utf-8")),
}));

it("scans a non-empty shipped source set (non-vacuous)", () => {
  expect(SOURCES.length).toBeGreaterThan(0);
});

describe("CG-G-S01a: 0 self-computation / 0 self-threshold", () => {
  // Each pattern is a way the dashboard would compute a metric or decide a
  // threshold itself, which would make it a second truth. If a real self-computed
  // threshold (`fps < target * 0.95`) is ever added, one of these bites.
  const COMPUTATION_PATTERNS: Array<[string, RegExp]> = [
    ["Math.*", /\bMath\./],
    ["number formatting", /\.(?:toFixed|toPrecision|toLocaleString)\s*\(/],
    ["numeric coercion", /\b(?:parseInt|parseFloat|Number)\s*\(/],
    // A comparison against a numeric literal (threshold decision). The lookbehind
    // excludes `=>` (arrow) and `===`/`!==`/`<=`/`>=` chains from false hits.
    ["comparison against a number", /(?<![=!<>])[<>]=?\s*-?\d/],
    // Multiplication or division between operands (metric arithmetic). Identifier-
    // aware so `free / total` is caught, not only literal-adjacent forms; the char
    // classes exclude JSX `</tag>` (`<` before) and `/>` (`>` after) from hits.
    ["arithmetic between operands", /[\w)\]]\s*[*/]\s*[\w(]/],
    // The NFR-GUI-011 target ratio (0.95) or camera ratio (0.9) — the thresholds
    // the backend owns; a copy here would be a self-threshold.
    ["a hardcoded 0.9x threshold", /0\.9[0-9]*/],
  ];

  it("contains no metric computation or threshold decision", () => {
    const offenders: string[] = [];
    for (const { path, computeCode } of SOURCES) {
      for (const [label, pattern] of COMPUTATION_PATTERNS) {
        if (pattern.test(computeCode)) {
          offenders.push(`${path}: ${label} (${pattern})`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("resolves a not-landed source to UNAVAILABLE with a presence check, not a threshold", () => {
    const severity = SOURCES.find(({ path }) => path.endsWith("severity.ts"));
    expect(severity).toBeDefined();
    expect(severity?.code).toMatch(/\?\?\s*UNAVAILABLE/);
  });
});

describe("CG-G-S01c: no hardcoded camera-tile-count constant", () => {
  const TILE_COUNT_CONSTANTS: RegExp[] = [
    /\b(?:TILE_COUNT|NUM_TILES|CAMERA_COUNT|MAX_TILES|TILES_PER_ROW|GRID_COLUMNS)\b/,
    /\b(?:tile|camera)[A-Za-z]*[Cc]ount\s*[:=]\s*\d+/,
    /\bcount(?:Of)?(?:Tiles|Cameras)\b\s*[:=]\s*\d+/,
  ];

  it("names no tile-count constant anywhere in the screen source", () => {
    const offenders: string[] = [];
    for (const { path, code } of SOURCES) {
      for (const pattern of TILE_COUNT_CONSTANTS) {
        if (pattern.test(code)) {
          offenders.push(`${path}: ${pattern}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("derives the tile set from the active-stream array length", () => {
    const view = SOURCES.find(({ path }) => path.endsWith("CameraStatusView.tsx"));
    expect(view).toBeDefined();
    expect(view?.code).toMatch(/cameras\.map/);
    expect(view?.code).toMatch(/cameras\.length/);
  });
});

describe("CG-G-S01d: cycle-time from PG-RT-001b only", () => {
  it("references the PG-RT-001b artifact as the cycle-time source", () => {
    const types = SOURCES.find(({ path }) => path.endsWith("types.ts"));
    expect(types?.code).toMatch(/PG-RT-001b/);
  });

  it("references the provisional PG-RT-001a nowhere", () => {
    for (const { path, code } of SOURCES) {
      expect(code, `${path} must not reference PG-RT-001a`).not.toMatch(/PG-RT-001a/);
    }
  });

  it("contains the colliding spec token nowhere in code or UI text", () => {
    // The token is left unwritten here on purpose; it is 'M' '-' '8'. Building it
    // from parts keeps this assertion from being its own only occurrence.
    const forbidden = new RegExp(["M", "8"].join("-"));
    for (const { path, code } of SOURCES) {
      expect(code, `${path} must not contain the colliding token`).not.toMatch(forbidden);
    }
  });
});

describe("facade / invariant I-2: no socket, no reconnect, no stamp, no external origin", () => {
  it("constructs no WebSocket and holds no reconnect path", () => {
    for (const { path, code } of SOURCES) {
      expect(code, `${path} must not open a socket`).not.toMatch(/\bWebSocket\b/);
      expect(code, `${path} must hold no reconnect path`).not.toMatch(
        /\breconnect\b|\bdisconnect\b|\bconnect\s*\(|재연결/,
      );
    }
  });

  it("reads no browser wall-clock (timestamps are the backend's)", () => {
    for (const { path, code } of SOURCES) {
      expect(code, `${path} must not read wall-clock`).not.toMatch(
        /strftime|toISOString|Date\.now\s*\(|new\s+Date\s*\(/,
      );
    }
  });

  it("reaches no external origin (air-gap, FR-GUI-008)", () => {
    for (const { path, code } of SOURCES) {
      expect(code, `${path} must reach no external URL`).not.toMatch(/https?:\/\//);
    }
  });
});
