// Static proofs the shipped S-13 source obeys the facade rules: it owns no
// port-map canon (CG-G-S13a, zero self-canon), and it holds no connect /
// disconnect / reconnect path (GUI invariant I-2 — a browser reconnect would
// destroy zeroing).
// These scan the shipped modules only; the *.test.* and testSupport files are
// scaffolding and are excluded.

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));

// The files that ship in the bundle (no tests, no test-only loaders).
const SHIPPED_FILES = [
  "screen.tsx",
  "PortCompareView.tsx",
  "RtCheckView.tsx",
  "DiagnosticBundleView.tsx",
  "ErrorLookupView.tsx",
  "ErrorEntryCard.tsx",
  "portCompare.ts",
  "rtCheck.ts",
  "diagnosticBundle.ts",
  "errorLookup.ts",
  "dataSource.ts",
  "types.ts",
];

function shipped(file: string): string {
  return readFileSync(resolve(HERE, file), "utf-8");
}

// The code of a file with comments removed. The facade rules bind the code, not
// the prose that documents them — this header, for instance, spells out the very
// words (connect/disconnect/reconnect) the scan forbids in code.
function codeOf(file: string): string {
  return shipped(file)
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/.*$/gm, "");
}

// The port numbers of the canon (01 §2.17 + 14 §2.1). None may be authored in the
// screen — the screen renders backend-served ports and owns none.
const CANON_PORTS = [8000, 5006, 8443, 8080, 5555];

describe("0 own port-map canon (CG-G-S13a)", () => {
  it("no shipped file contains any canon port literal", () => {
    for (const file of SHIPPED_FILES) {
      const source = codeOf(file);
      for (const port of CANON_PORTS) {
        expect(source, `${file} must not author canon port ${port}`).not.toMatch(
          new RegExp(`\\b${port}\\b`),
        );
      }
    }
  });

  it("the port-compare module authors no port-range integer literal at all", () => {
    for (const file of ["portCompare.ts", "PortCompareView.tsx"]) {
      const portRange = [...codeOf(file).matchAll(/\b(\d{4,5})\b/g)]
        .map((match) => Number(match[1]))
        .filter((value) => value >= 1024 && value <= 65535);
      expect(portRange, `${file} port-range literals`).toEqual([]);
    }
  });
});

describe("no reconnect path (invariant I-2)", () => {
  it("no shipped file references connect / disconnect / reconnect", () => {
    const forbidden = /\b(reconnect|disconnect)\b|\bconnect\s*\(|재연결/;
    for (const file of SHIPPED_FILES) {
      expect(codeOf(file), `${file} must hold no reconnect path`).not.toMatch(forbidden);
    }
  });

  it("uses no WebSocket in the system screen — its data is REST host reads", () => {
    for (const file of SHIPPED_FILES) {
      expect(codeOf(file)).not.toMatch(/\bWebSocket\b|new\s+WebSocket/);
    }
  });
});
