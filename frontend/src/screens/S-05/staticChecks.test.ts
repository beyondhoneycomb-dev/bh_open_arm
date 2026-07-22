// Facade static checks for the teleop screen (WP-G-S05, §0.2). The teleop truth
// lives in the backend `Teleoperator` / safety gate; the screen renders it and sends
// intent. These scans prove the browser re-implements none of that truth:
//
//   - no deg<->rad conversion (CTR-UNIT@v1 is the backend's);
//   - no connect/disconnect/reconnect path (I-2: connect() re-zeroes);
//   - no self-clamp (the scale/param ranges are display bounds, the backend clamps);
//   - no One-Euro / phase-lag math (FR-GUI-106: the smoother is in the backend; tau
//     is a backend value the screen renders, never derives — so Math.PI must not
//     appear in production source).
//
// The scan strips comments before matching, exactly as the sibling S-04 scan and the
// WP-G-04 CG-G-04a scan do: the comments name the forbidden symbols to document the
// invariants, and Vite drops them from the bundle. Data/UI text carries no code-call
// identifier the patterns target (the forbidden connect()/disconnect() call literals
// are kept out of the source entirely, not hidden inside strings).

import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, extname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const SCREEN_ROOT = dirname(fileURLToPath(import.meta.url));
const SCANNED_EXTENSIONS: ReadonlySet<string> = new Set([".ts", ".tsx"]);

function isTestFile(path: string): boolean {
  return /\.test\.(ts|tsx)$/.test(path);
}

// Strip block then line comments; the `://` guard keeps a URL in a code string from
// being read as a line comment. Comments name the forbidden symbols to explain the
// invariants and Vite drops them from the bundle, so a symbol in a comment is neither
// a call nor a shipped label.
function stripComments(text: string): string {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/(?<!:)\/\/.*$/gm, " ");
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

const CONVERSION_PATTERNS: readonly RegExp[] = [
  /\b(?:DEG2RAD|RAD2DEG|deg2rad|rad2deg|degToRad|radToDeg|toRadians|toDegrees)\b/,
  /Math\s*\.\s*PI\s*\/\s*180/,
  /180\s*\/\s*Math\s*\.\s*PI/,
  /\b57\.29\d*/,
  /\b0\.0174\d*/,
];

// connect()/disconnect()/reconnect: none may appear (I-2). Session control is a WS
// intent, never a link re-open.
const RECONNECT_PATTERNS: readonly RegExp[] = [
  /\breconnect\b/i,
  /\bdisconnect\b/i,
  /\bconnect\s*\(/,
];

// A self-implemented clamp / min-max fold used to bound a value.
const CLAMP_PATTERNS: readonly RegExp[] = [
  /\bclamp\s*\(/i,
  /Math\s*\.\s*min\s*\(/,
  /Math\s*\.\s*max\s*\(/,
];

// The One-Euro smoother and its phase lag are the backend's (FR-GUI-106). The browser
// renders the backend tau value and derives none, so no smoother math constant may
// appear in production source.
const SMOOTHER_MATH_PATTERNS: readonly RegExp[] = [
  /Math\s*\.\s*PI/,
  /Math\s*\.\s*exp\s*\(/,
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

describe("teleop screen is a facade (WP-G-S05, §0.2)", () => {
  it("converts no deg<->rad in screen source (CTR-UNIT@v1)", () => {
    expect(scan(CONVERSION_PATTERNS)).toEqual([]);
  });

  it("names no connect/disconnect/reconnect symbol in screen source (I-2)", () => {
    expect(scan(RECONNECT_PATTERNS)).toEqual([]);
  });

  it("self-implements no clamp / min-max bound in screen source", () => {
    expect(scan(CLAMP_PATTERNS)).toEqual([]);
  });

  it("derives no One-Euro / phase-lag math in screen source (FR-GUI-106)", () => {
    expect(scan(SMOOTHER_MATH_PATTERNS)).toEqual([]);
  });
});
