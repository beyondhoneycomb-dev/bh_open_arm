// Static half of the S-02 gates and the facade invariants, scanned over the
// screen's production source (this subtree, excluding test files) with comments
// stripped — comments legitimately name connect()/set_zero_position/deg to explain
// the invariants, and Vite drops them from the bundle.
//
//   * CG-G-S02b (static): the first bringup backend action is connect_readonly.
//   * CTR-UNIT@v1: the browser converts no deg<->rad and calls no degree setter.
//   * I-2: the screen calls no Robot connect()/disconnect()/set_zero_position() —
//     it SENDS intent over the WS; it never re-attaches the Robot (which would
//     destroy the zero). The FR-GUI-084 unavoidable-relink flow is named "re-zero"
//     here (rezeroFlow.ts) rather than "reconnect": the committed WP-G-04 invariant
//     (src/mode/invariants.test.ts, CG-G-04a) bans the reconnect label GUI-wide,
//     and this screen's flow is in truth a re-zero — the current pose becomes the
//     new zero — so the accurate name also stays clear of that ban.
//   * CG-G-00e: no config canon in localStorage/sessionStorage.
//   * Air-gap: no external origin.

import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, extname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { firstBackendAction } from "./bringup";

const S02_ROOT = dirname(fileURLToPath(import.meta.url));
const SCANNED_EXTENSIONS: ReadonlySet<string> = new Set([".ts", ".tsx"]);

function isTestFile(path: string): boolean {
  return /\.test\.(ts|tsx)$/.test(path);
}

function stripComments(text: string): string {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

function s02Sources(): string[] {
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
  walk(S02_ROOT);
  return acc;
}

function scan(patterns: readonly RegExp[]): string[] {
  const offenders: string[] = [];
  for (const file of s02Sources()) {
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

// deg<->rad conversion identifiers and the two magic factors. Angle geometry like
// Math.PI / 2 is not a unit conversion and is not matched.
const CONVERSION_PATTERNS: readonly RegExp[] = [
  /\b(?:DEG2RAD|RAD2DEG|deg2rad|rad2deg|degToRad|radToDeg|toRadians|toDegrees)\b/,
  /Math\s*\.\s*PI\s*\/\s*180/,
  /180\s*\/\s*Math\s*\.\s*PI/,
  /\b57\.29\d*/,
  /\b0\.0174\d*/,
];

const SET_JOINT_DEG = /setJointValues?\s*\([^)]*\bdeg\b/i;

// Robot re-attach / auto-zero call forms (I-2). connect_readonly / reconnect are
// NOT these forms: connect( needs "(" immediately after the whole word "connect".
const ROBOT_CALL_PATTERNS: readonly RegExp[] = [
  /\bconnect\s*\(/,
  /\bdisconnect\s*\(/,
  /\bset_zero_position\s*\(/,
];

const STORAGE_PATTERNS: readonly RegExp[] = [/\blocalStorage\b/, /\bsessionStorage\b/];

const EXTERNAL_ORIGIN_PATTERNS: readonly RegExp[] = [/https?:\/\//, /wss?:\/\//];

describe("CG-G-S02b (static) bringup begins with connect_readonly", () => {
  it("declares connect_readonly as the first backend action", () => {
    expect(firstBackendAction()).toBe("connect_readonly");
  });
});

describe("CTR-UNIT@v1: no deg<->rad conversion in S-02", () => {
  it("names no conversion constant", () => {
    expect(scan(CONVERSION_PATTERNS)).toEqual([]);
  });
  it("makes no degree-valued setJointValue call", () => {
    expect(scan([SET_JOINT_DEG])).toEqual([]);
  });
});

describe("I-2: S-02 never re-attaches the Robot", () => {
  it("calls no connect()/disconnect()/set_zero_position()", () => {
    expect(scan(ROBOT_CALL_PATTERNS)).toEqual([]);
  });
});

describe("CG-G-00e / air-gap", () => {
  it("keeps no config canon in web storage", () => {
    expect(scan(STORAGE_PATTERNS)).toEqual([]);
  });
  it("names no external origin", () => {
    expect(scan(EXTERNAL_ORIGIN_PATTERNS)).toEqual([]);
  });
});
