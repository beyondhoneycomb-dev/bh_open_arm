// Static scans over the S-03 production source (every non-test, non-testSupport
// file under this screen). Three acceptance checks are structural invariants a
// render test cannot prove absent, so they are scanned the way the WP-G-03 source
// is scanned: CG-G-S03a (no N/Nm grasp-force label), CG-G-S03b (no temperature
// polling — state-frame parse only), CG-G-S03f (no raw literal 50/30 gripper
// speed; vMax is injected). Comments are stripped first so English prose that
// merely names the forbidden tokens (e.g. "newton-metres") is not a false hit.

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
      // testSupport holds test-only fixtures; it never enters the bundle.
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

const SOURCES = collectSources(SCREEN_ROOT, []).map((path) => ({
  path,
  code: stripComments(readFileSync(path, "utf-8")),
}));

function sourceEndingWith(suffix: string): { path: string; code: string } {
  const found = SOURCES.find(({ path }) => path.endsWith(suffix));
  if (!found) {
    throw new Error(`expected a source file ending with ${suffix}`);
  }
  return found;
}

describe("CG-G-S03a: no N/Nm grasp-force label", () => {
  // The gripper force is the only grasp force; it must be per-unit, never a
  // force unit. Motor T_MAX (Nm) is a different quantity and lives in a different
  // file, so the newton/newton-metre ban is scoped to the gripper panel.
  const GRASP_FORCE_UNIT = /(파지력|grasp[- ]?force|graspforce)[\s\S]{0,40}(\bNm\b|\bN\b)/i;

  it("labels no grasp force in newtons or newton-metres anywhere in the screen", () => {
    const offenders = SOURCES.filter(({ code }) => GRASP_FORCE_UNIT.test(code)).map((s) => s.path);
    expect(offenders).toEqual([]);
  });

  it("carries no Nm token and no standalone N unit in the gripper panel", () => {
    const gripper = sourceEndingWith("GripperPanel.tsx");
    expect(gripper.code).not.toMatch(/\bNm\b/);
    expect(gripper.code).not.toMatch(/["'`]\s*N\s*["'`]/);
    // The force is labelled through the per-unit constant, never a force unit.
    expect(gripper.code).toMatch(/TORQUE_PU_LABEL/);
  });
});

describe("CG-G-S03b: no temperature polling — state-frame parse only", () => {
  it("issues no HTTP/fetch/XHR request from any screen source", () => {
    for (const { path, code } of SOURCES) {
      expect(code, `${path} fetch`).not.toMatch(/\bfetch\s*\(/);
      expect(code, `${path} XHR`).not.toMatch(/XMLHttpRequest/);
    }
  });

  it("runs no interval/timeout poll loop in any screen source", () => {
    for (const { path, code } of SOURCES) {
      expect(code, `${path} setInterval`).not.toMatch(/setInterval\s*\(/);
      expect(code, `${path} setTimeout`).not.toMatch(/setTimeout\s*\(/);
    }
  });

  it("names no poll path anywhere in the screen", () => {
    // With no request primitive (above) and no poll word, temperature can only
    // come from the state frame the screen parses.
    for (const { path, code } of SOURCES) {
      expect(code, `${path} poll`).not.toMatch(/\bpoll(ing)?\b/i);
    }
  });

  it("sources temperature from the state-frame parser", () => {
    const domain = sourceEndingWith("motorDomain.ts");
    expect(domain.code).toMatch(/parseMotorStatesFromFrame/);
  });
});

describe("CG-G-S03f: gripper speed carries no raw literal 50/30", () => {
  it("exposes no literal 50 in any production source", () => {
    const offenders = SOURCES.filter(({ code }) => /\b50(\.0+)?\b/.test(code)).map((s) => s.path);
    expect(offenders).toEqual([]);
  });

  it("hardcodes no vMax literal 30 in the gripper panel — it is injected", () => {
    const gripper = sourceEndingWith("GripperPanel.tsx");
    expect(gripper.code).not.toMatch(/\b30(\.0+)?\b/);
    expect(gripper.code).toMatch(/effectiveGripperSpeedRadS/);
    expect(gripper.code).toMatch(/motorVMaxRadS/);
  });
});
