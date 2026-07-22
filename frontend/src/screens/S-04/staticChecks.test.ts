// CG-G-S04a (static): the manual screen does NOT self-implement clamp or velocity
// limiting. The jog math, the two-stage clamp (mechanical then operating limit)
// and the velocity/step guards are the backend MAN domain's (FR-MAN-007/011/012);
// a second implementation in the browser would let the screen disagree with the
// robot about limits and lie (CG-G-S04a negative branch).
//
// It also reinforces two GUI-wide invariants on this subtree: the browser converts
// no deg<->rad (CTR-UNIT@v1 is the backend's) and the screen holds no
// reconnect/connect path (I-2 — connect() re-zeroes).
//
// The scan reads this subtree's production source (excluding *.test files) with
// comments stripped, exactly as the viewport's scan does: comments legitimately
// name "clamp" and "connect()" to explain the invariant, and Vite drops them from
// the bundle. Data identifiers like the backend limit-set name "soft_clamp" are
// values, not clamp logic, so the patterns target clamp/limit CALLS and symbols,
// not every occurrence of the substring.

import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, extname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const SCREEN_ROOT = dirname(fileURLToPath(import.meta.url));
const SCANNED_EXTENSIONS: ReadonlySet<string> = new Set([".ts", ".tsx"]);

function isTestFile(path: string): boolean {
  return /\.test\.(ts|tsx)$/.test(path);
}

function stripComments(text: string): string {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

function screenSources(): string[] {
  const acc: string[] = [];
  const walk = (dir: string): void => {
    for (const name of readdirSync(dir)) {
      const full = join(dir, name);
      if (statSync(full).isDirectory()) {
        walk(full);
      } else if (SCANNED_EXTENSIONS.has(extname(full)) && !isTestFile(full)) {
        acc.push(full);
      }
    }
  };
  walk(SCREEN_ROOT);
  return acc;
}

// A clamp CALL or a min/max fold used to bound a value — the shape of a
// self-implemented clamp. `clamp(` requires the `(` so the backend limit-set name
// "soft_clamp" (a value) is not matched.
const CLAMP_PATTERNS: readonly RegExp[] = [
  /\bclamp\s*\(/i,
  /Math\s*\.\s*min\s*\(/,
  /Math\s*\.\s*max\s*\(/,
];

// A self-implemented velocity/acceleration/jerk limit. Readout field names like
// `velocityRadPerSec` (a backend value the screen displays) are not limits and are
// not matched; only the *_limit / max* symbols are.
const VELOCITY_LIMIT_PATTERNS: readonly RegExp[] = [
  /velocity_limit/i,
  /velocityLimit/,
  /acceleration_limit/i,
  /accelerationLimit/,
  /\bjerk\b/i,
  /\bMAX_VELOCITY\b/,
  /\bmaxVelocity\b/,
];

// deg<->rad conversion identifiers and the magic factors (CTR-UNIT@v1). Field
// names carrying a "Deg"/"Rad" suffix are units on a value, not a conversion.
const CONVERSION_PATTERNS: readonly RegExp[] = [
  /\b(?:DEG2RAD|RAD2DEG|deg2rad|rad2deg|degToRad|radToDeg|toRadians|toDegrees)\b/,
  /Math\s*\.\s*PI\s*\/\s*180/,
  /180\s*\/\s*Math\s*\.\s*PI/,
  /\b57\.29\d*/,
  /\b0\.0174\d*/,
];

// connect()/disconnect()/reconnect: none may appear (I-2). Arming is enable_torque.
const RECONNECT_PATTERNS: readonly RegExp[] = [
  /\breconnect\b/i,
  /\bdisconnect\b/i,
  /\bconnect\s*\(/,
];

function scan(patterns: readonly RegExp[]): string[] {
  const offenders: string[] = [];
  for (const file of screenSources()) {
    const text = stripComments(readFileSync(file, "utf-8"));
    for (const pattern of patterns) {
      const match = pattern.exec(text);
      if (match) {
        offenders.push(`${file}: ${match[0]}`);
      }
    }
  }
  return offenders;
}

describe("CG-G-S04a manual screen self-implements no clamp / velocity limit", () => {
  it("names no clamp fold in screen source", () => {
    expect(scan(CLAMP_PATTERNS)).toEqual([]);
  });

  it("names no velocity/acceleration/jerk limit in screen source", () => {
    expect(scan(VELOCITY_LIMIT_PATTERNS)).toEqual([]);
  });

  it("converts no deg<->rad in screen source (CTR-UNIT@v1)", () => {
    expect(scan(CONVERSION_PATTERNS)).toEqual([]);
  });

  it("names no connect/disconnect/reconnect symbol in screen source (I-2)", () => {
    expect(scan(RECONNECT_PATTERNS)).toEqual([]);
  });
});
