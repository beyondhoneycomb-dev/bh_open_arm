// The consume-the-frozen-contract proof for CTR-ERR@v1. Reads the frozen
// `contracts/errors/error_registry.yaml` and asserts the browser mirror in
// errors.ts agrees on the four severity levels, the closed domain set, and the
// OA-* code grammar — and that every registered code parses under that grammar.
// A registry change that adds a domain or severity fails this test (CR-2).

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  isOaCode,
  isSeverityName,
  OA_CODE_PATTERN,
  OA_DOMAINS,
  oaDomainOf,
  SEVERITY_LEVELS,
} from "./errors";

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const registryText = readFileSync(
  resolve(REPO_ROOT, "contracts/errors/error_registry.yaml"),
  "utf-8",
);

// A minimal block reader: the values indented under a top-level key, until the
// next top-level key. Avoids pulling a YAML dependency into the frontend lane.
function indentedBlock(key: string): string[] {
  const lines = registryText.split("\n");
  const start = lines.findIndex((line) => line === `${key}:`);
  if (start < 0) {
    return [];
  }
  const block: string[] = [];
  for (let index = start + 1; index < lines.length; index += 1) {
    const line = lines[index];
    if (line.trim() === "" || line.startsWith("#")) {
      continue;
    }
    if (!/^\s/.test(line)) {
      break;
    }
    block.push(line);
  }
  return block;
}

describe("CTR-ERR@v1 mirror equals the frozen registry", () => {
  it("agrees on the four severity levels", () => {
    const parsed: Record<string, number> = {};
    for (const line of indentedBlock("severity_levels")) {
      const match = /^\s+([A-Z]+):\s*(\d+)\s*$/.exec(line);
      if (match) {
        parsed[match[1]] = Number(match[2]);
      }
    }
    expect(parsed).toEqual(SEVERITY_LEVELS);
    for (const name of Object.keys(parsed)) {
      expect(isSeverityName(name)).toBe(true);
    }
  });

  it("agrees on the closed domain set", () => {
    const domains: string[] = [];
    for (const line of indentedBlock("domains")) {
      const match = /^\s*-\s*(OA-[A-Z]+)\s*$/.exec(line);
      if (match) {
        domains.push(match[1]);
      }
    }
    expect(new Set(domains)).toEqual(new Set(OA_DOMAINS));
  });

  it("parses every registered code under the mirror grammar and domain set", () => {
    const codes = [...registryText.matchAll(/code:\s*(OA-[A-Z0-9-]+)/g)].map((match) => match[1]);
    expect(codes.length).toBeGreaterThan(0);
    for (const code of codes) {
      expect(OA_CODE_PATTERN.test(code)).toBe(true);
      expect(isOaCode(code)).toBe(true);
      expect(oaDomainOf(code)).not.toBeNull();
    }
  });

  it("rejects a malformed code", () => {
    expect(isOaCode("OA-nope-1")).toBe(false);
    expect(isOaCode("MOT-008")).toBe(false);
    expect(oaDomainOf("OA-XXX-000")).toBeNull();
  });
});
