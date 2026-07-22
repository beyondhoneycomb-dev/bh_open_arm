// Consume the frozen CTR-ERR@v1 contract as a test target: read the backend
// registry file directly and assert the browser mirror still agrees with it, so
// a change to the frozen severity levels or domain set breaks this test instead
// of silently desynchronising the notification center. The YAML is read as text
// and scanned with small regexes rather than parsed with a library dependency
// the frontend does not declare.

import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import {
  OA_DOMAINS,
  Severity,
  holdsBadgeUntilAck,
  isValidErrorCode,
} from "./errorCodes";
import { repoFile } from "../testSupport/repoRoot";

const REGISTRY_YAML = readFileSync(repoFile("contracts/errors/error_registry.yaml"), "utf-8");

function frozenSeverityLevels(): Record<string, number> {
  const block = /severity_levels:\n((?:\s+[A-Z]+:\s*\d+\n)+)/.exec(REGISTRY_YAML);
  if (!block) {
    throw new Error("severity_levels block not found in frozen CTR-ERR registry");
  }
  const levels: Record<string, number> = {};
  for (const line of block[1].matchAll(/\s+([A-Z]+):\s*(\d+)/g)) {
    levels[line[1]] = Number(line[2]);
  }
  return levels;
}

function frozenDomains(): string[] {
  const block = /\ndomains:\n((?:\s+-\s*OA-[A-Z]+\n)+)/.exec(REGISTRY_YAML);
  if (!block) {
    throw new Error("domains block not found in frozen CTR-ERR registry");
  }
  return [...block[1].matchAll(/-\s*(OA-[A-Z]+)/g)].map((m) => m[1]);
}

describe("CTR-ERR@v1 mirror agrees with the frozen registry", () => {
  it("pins the same four severity levels and values", () => {
    expect(frozenSeverityLevels()).toEqual({
      OK: Severity.OK,
      WARN: Severity.WARN,
      ERROR: Severity.ERROR,
      STALE: Severity.STALE,
    });
  });

  it("pins the same closed domain set", () => {
    expect(frozenDomains()).toEqual([...OA_DOMAINS]);
  });
});

describe("severity badge-hold rule (CG-G-03g)", () => {
  it("holds the badge for ERROR and above, not for OK/WARN", () => {
    expect(holdsBadgeUntilAck(Severity.OK)).toBe(false);
    expect(holdsBadgeUntilAck(Severity.WARN)).toBe(false);
    expect(holdsBadgeUntilAck(Severity.ERROR)).toBe(true);
    expect(holdsBadgeUntilAck(Severity.STALE)).toBe(true);
  });
});

describe("OA-* code validation", () => {
  it("accepts hex numbers in a closed domain and rejects everything else", () => {
    expect(isValidErrorCode("OA-MOT-00A")).toBe(true);
    expect(isValidErrorCode("OA-CAN-001")).toBe(true);
    expect(isValidErrorCode("OA-XXX-001")).toBe(false);
    expect(isValidErrorCode("OA-MOT-00G")).toBe(false);
    expect(isValidErrorCode("MOT-001")).toBe(false);
  });
});
