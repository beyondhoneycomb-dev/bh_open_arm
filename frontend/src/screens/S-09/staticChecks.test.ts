// The static-scan gates for WP-G-S09. They read the S-09 source tree as text and
// assert structural invariants a runtime test cannot: the sim<->real swap path
// names no reconnect / connect / disconnect symbol (CG-G-S09c), and no MJCF value
// is authored as a hardware-spec basis (CG-G-S09a, static half). Comments are
// stripped first, so prose that names the forbidden concepts to explain the
// invariants — "the swap performs no reconnect" — does not trip the scan.

import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const S09_DIR = dirname(fileURLToPath(import.meta.url));

function isTestFile(name: string): boolean {
  return /\.test\.tsx?$/.test(name);
}

function productionFiles(): string[] {
  return readdirSync(S09_DIR)
    .filter((name) => /\.tsx?$/.test(name) && !isTestFile(name))
    .map((name) => join(S09_DIR, name));
}

function stripComments(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(?<!:)\/\/.*$/gm, "");
}

function readStripped(path: string): string {
  return stripComments(readFileSync(path, "utf-8"));
}

describe("CG-G-S09c sim<->real swap carries no reconnect symbol", () => {
  it("names no reconnect / disconnect / connect symbol in production source", () => {
    const forbidden: RegExp[] = [/\breconnect\b/i, /\bdisconnect\b/i, /\bconnect\b/, /재연결/];
    const offenders: string[] = [];
    for (const path of productionFiles()) {
      const text = readStripped(path);
      for (const pattern of forbidden) {
        if (pattern.test(text)) {
          offenders.push(`${path}: ${pattern}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});

describe("CG-G-S09a no MJCF value authored as a hardware-spec basis", () => {
  const domainPath = join(S09_DIR, "simDomain.ts");

  it("declares every fact basis as sim-asset-only, and no other basis value", () => {
    const bases = readStripped(domainPath).match(/basis:\s*"[^"]*"/g) ?? [];
    expect(bases.length).toBeGreaterThan(0);
    for (const basis of bases) {
      expect(basis).toBe('basis: "sim-asset-only"');
    }
  });

  it("authors no hardware-spec basis token anywhere in production source", () => {
    const offenders: string[] = [];
    for (const path of productionFiles()) {
      const text = readStripped(path);
      if (/["'](hardware[-_]?spec|hardware-spec-basis)["']/i.test(text)) {
        offenders.push(path);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("keeps the standing not-a-hardware-spec disclaimer and the sim-asset tag", () => {
    const domain = readFileSync(domainPath, "utf-8");
    expect(domain).toContain("MJCF_NOT_HARDWARE_SPEC_DISCLAIMER");
    expect(domain).toContain("SIM_ASSET_TAG");
  });
});
