// CG-G-02a (static): the browser does not convert deg<->rad and does not call a
// degree-valued joint setter — CTR-UNIT@v1 (backend) owns the deg/rad boundary and
// the joint namespace. It also reinforces I-2 / CG-G-02e: the viewport's recovery
// path holds no reconnect/connect/disconnect, because connect() destroys the
// zeroing and the browser retries only the WebSocket (WP-G-01's concern).
//
// The scan reads the viewport's production source (this subtree, excluding test
// files) with comments stripped: comments legitimately discuss deg/rad and
// connect() to explain the invariant, and Vite drops them from the bundle, so a
// token inside a comment is neither a runtime conversion nor a runtime call.

import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, extname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const VIEWPORT_ROOT = dirname(fileURLToPath(import.meta.url));
const SCANNED_EXTENSIONS: ReadonlySet<string> = new Set([".ts", ".tsx"]);

function isTestFile(path: string): boolean {
  return /\.test\.(ts|tsx)$/.test(path);
}

// Remove block comments and line comments. The line-comment strip guards against
// a `://` in code (a URL or a `package://` regex) being read as a comment start.
function stripComments(text: string): string {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

function viewportSources(): string[] {
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
  walk(VIEWPORT_ROOT);
  return acc;
}

// deg<->rad conversion identifiers and the two magic factors (pi/180, 180/pi) plus
// their decimal forms. Angle geometry like `Math.PI / 2` is a rotation, not a unit
// conversion, and is deliberately not matched.
const CONVERSION_PATTERNS: readonly RegExp[] = [
  /\b(?:DEG2RAD|RAD2DEG|deg2rad|rad2deg|degToRad|radToDeg|toRadians|toDegrees)\b/,
  /Math\s*\.\s*PI\s*\/\s*180/,
  /180\s*\/\s*Math\s*\.\s*PI/,
  /\b57\.29\d*/,
  /\b0\.0174\d*/,
];

// setJointValue(name, <deg-valued arg>): any setJointValue/setJointValues call
// whose argument list mentions a degree token. The viewport uses only the batch,
// radian path, so this is empty by construction.
const SET_JOINT_DEG = /setJointValues?\s*\([^)]*\bdeg\b/i;

// connect()/disconnect()/reconnect: none may appear in the viewport's recovery.
const RECONNECT_PATTERNS: readonly RegExp[] = [
  /\breconnect\b/i,
  /\bdisconnect\b/i,
  /\bconnect\s*\(/,
];

describe("CG-G-02a browser does not convert deg<->rad", () => {
  it("names no deg<->rad conversion constant in viewport source", () => {
    const offenders: string[] = [];
    for (const file of viewportSources()) {
      const text = stripComments(readFileSync(file, "utf-8"));
      for (const pattern of CONVERSION_PATTERNS) {
        const match = pattern.exec(text);
        if (match) {
          offenders.push(`${file}: ${match[0]}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("makes no degree-valued setJointValue call", () => {
    const offenders: string[] = [];
    for (const file of viewportSources()) {
      const text = stripComments(readFileSync(file, "utf-8"));
      if (SET_JOINT_DEG.test(text)) {
        offenders.push(file);
      }
    }
    expect(offenders).toEqual([]);
  });
});

describe("CG-G-02e recovery path holds no reconnect (I-2)", () => {
  it("names no connect/disconnect/reconnect symbol in viewport source", () => {
    const offenders: string[] = [];
    for (const file of viewportSources()) {
      const text = stripComments(readFileSync(file, "utf-8"));
      for (const pattern of RECONNECT_PATTERNS) {
        const match = pattern.exec(text);
        if (match) {
          offenders.push(`${file}: ${match[0]}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
