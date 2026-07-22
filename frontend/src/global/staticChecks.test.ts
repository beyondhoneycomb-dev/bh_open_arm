// Static scans over the WP-G-03 production source (every non-test file under
// src/global). CG-G-03c requires zero individual-setting UI path for
// use_velocity_and_torque, and CG-G-03a requires the two stops never collapse
// into one control. Both are structural invariants a render test cannot prove
// absent, so they are checked by scanning the source the way the air-gap check
// scans for external URLs.

import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, extname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const GLOBAL_ROOT = dirname(fileURLToPath(import.meta.url));
const SCANNED_EXTENSIONS: ReadonlySet<string> = new Set([".ts", ".tsx"]);

function isTestFile(path: string): boolean {
  return /\.test\.(ts|tsx)$/.test(path);
}

function collectSources(dir: string, acc: string[]): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      // Test-support helpers are test-only and never bundled.
      if (name !== "testSupport") {
        collectSources(full, acc);
      }
    } else if (SCANNED_EXTENSIONS.has(extname(full)) && !isTestFile(full)) {
      acc.push(full);
    }
  }
  return acc;
}

function stripComments(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(?<!:)\/\/.*$/gm, "");
}

const SOURCES = collectSources(GLOBAL_ROOT, []).map((path) => ({
  path,
  code: stripComments(readFileSync(path, "utf-8")),
}));

describe("CG-G-03c: no individual-setting path for use_velocity_and_torque", () => {
  // Per-arm identifiers that would let follower and leader be set separately. The
  // flag is a coupled single switch (F-4'): a per-arm setter is the failure.
  const PER_ARM_PATTERNS: RegExp[] = [
    /follower[_A-Za-z]*(velocity|torque)/i,
    /leader[_A-Za-z]*(velocity|torque)/i,
    /(velocity|torque)[_A-Za-z]*follower/i,
    /(velocity|torque)[_A-Za-z]*leader/i,
    /set(Follower|Leader)VelocityTorque/,
  ];

  it("names no per-arm velocity/torque setter anywhere in the WP source", () => {
    const offenders: string[] = [];
    for (const { path, code } of SOURCES) {
      for (const pattern of PER_ARM_PATTERNS) {
        if (pattern.test(code)) {
          offenders.push(`${path}: ${pattern}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("exposes the coupled single mutator", () => {
    const hasCoupledSetter = SOURCES.some(({ code }) =>
      /setVelocityTorqueCoupled/.test(code),
    );
    expect(hasCoupledSetter).toBe(true);
  });
});

describe("CG-G-03a: the two stops never merge into one control", () => {
  it("keeps two distinct handler props, never a single merged stop dispatcher", () => {
    const stopControls = SOURCES.find(({ path }) => path.endsWith("StopControls.tsx"));
    expect(stopControls).toBeDefined();
    const code = stopControls?.code ?? "";
    expect(code).toMatch(/onSoftStop/);
    expect(code).toMatch(/onHardEStop/);
    // No combined dispatcher that takes a stop kind and branches to both outcomes.
    expect(code).not.toMatch(/onStop\s*\(\s*kind/);
    expect(code).not.toMatch(/function\s+stop\s*\(\s*kind/);
  });

  it("renders both stop kinds with distinct classes and shows the drop warning", () => {
    const stopControls = SOURCES.find(({ path }) => path.endsWith("StopControls.tsx"));
    const code = stopControls?.code ?? "";
    expect(code).toMatch(/oa-stop--soft/);
    expect(code).toMatch(/oa-stop--hard/);
    expect(code).toMatch(/HARD_ESTOP_DROP_WARNING/);
  });
});
