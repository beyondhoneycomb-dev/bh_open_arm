// Static proofs the shipped S-11 source obeys the facade and inference/eval invariants.
// These are the CG-G-S11 guards a render test cannot prove absent, so they are scanned the
// way the sibling screens scan their structural rules. The scan reads the shipped .ts/.tsx
// modules only; *.test.* and the stylesheet are excluded. Comments are stripped first, so
// these headers — which necessarily spell out the very tokens the scans forbid
// (lerobot-eval, a bare point estimate) — are never themselves hits.
//
//   - CG-G-S11b: the raw report field `pointEstimate` is READ (member access) only in
//     successRate.ts, which pairs it with the Wilson CI; everywhere else the rate goes
//     through the CI-bearing display, so there is no site that shows a point estimate alone.
//     (Constructing the field in a fixture/shape is data population, not a display read.)
//   - CG-G-S11d: no `lerobot-eval` call path anywhere (the real engine is `lerobot-rollout`).
//   - CG-G-S11e: exactly one start op exists, and exactly one gated site emits it, so LOCAL
//     and ASYNC resolve to one start code path.
//   - CG-G-S11a: the screen composes the schema lock and disables every control on it.
//   - facade / I-2: no socket, no reconnect, no browser-side wall-clock stamp.

import { readFileSync, readdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));

const SHIPPED_FILES = readdirSync(HERE).filter(
  (name) => /\.(ts|tsx)$/.test(name) && !name.includes(".test."),
);

function shipped(file: string): string {
  return readFileSync(resolve(HERE, file), "utf-8");
}

// The code of a file with comments removed. The rules bind the code, not the prose that
// documents them. The `:` guard keeps `https://` and `://`-style tokens intact.
function codeOf(file: string): string {
  return shipped(file)
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

it("scans a non-empty shipped source set (non-vacuous)", () => {
  expect(SHIPPED_FILES.length).toBeGreaterThan(0);
});

describe("CG-G-S11b: no bare point estimate — always with its Wilson CI", () => {
  // A READ of the raw report field via member access (`x.pointEstimate`), distinguished
  // from the formatted `pointEstimatePct` display field by a negative lookahead. This is
  // the site that could show a point estimate; populating the field in a fixture/shape
  // (`pointEstimate:`) is data construction, not a display, and does not match.
  const RAW_POINT_ESTIMATE_READ = /\.pointEstimate(?![A-Za-z0-9_])/;
  const ALLOWED = new Set(["successRate.ts"]);

  it("reads the raw pointEstimate only in successRate.ts", () => {
    for (const file of SHIPPED_FILES) {
      if (ALLOWED.has(file)) {
        continue;
      }
      expect(codeOf(file), `${file} must not read the raw pointEstimate`).not.toMatch(
        RAW_POINT_ESTIMATE_READ,
      );
    }
  });

  it("successRate.ts reads the point estimate on the same footing as the Wilson CI", () => {
    const code = codeOf("successRate.ts");
    expect(code).toMatch(RAW_POINT_ESTIMATE_READ);
    // The sole reader also reads the Wilson interval, so the two are produced together.
    expect(code).toMatch(/ciWilson95/);
  });

  it("the panel renders the point estimate and the CI in the one element", () => {
    const panel = codeOf("SuccessRatePanelView.tsx");
    expect(panel).toMatch(/data-testid="success-rate"/);
    expect(panel).toMatch(/pointEstimatePct/);
    expect(panel).toMatch(/wilsonText/);
    // The 2-landing branch shows no number.
    expect(panel).toMatch(/success-rate-pending/);
  });
});

describe("CG-G-S11d: no lerobot-eval call path (the engine is lerobot-rollout)", () => {
  it("names no lerobot-eval anywhere in the shipped code", () => {
    for (const file of SHIPPED_FILES) {
      expect(codeOf(file), `${file} must not reference lerobot-eval`).not.toMatch(
        /lerobot[-_]eval/i,
      );
    }
  });

  it("names the real-robot rollout engine", () => {
    const code = codeOf("types.ts");
    expect(code).toMatch(/lerobot-rollout/);
  });
});

describe("CG-G-S11e: LOCAL/ASYNC resolve to one start code path", () => {
  it("declares exactly one start op, and it is start_rollout", () => {
    const ops = [...codeOf("commands.ts").matchAll(/\bop:\s*"([^"]+)"/g)].map((m) => m[1]);
    const starters = ops.filter((op) => /start|launch/i.test(op));
    expect(starters).toEqual(["start_rollout"]);
  });

  it("the one builder makes the command with the form as a field, not a fork", () => {
    const code = codeOf("rolloutMode.ts");
    const builds = [...code.matchAll(/op:\s*"start_rollout"/g)];
    expect(builds.length).toBe(1);
    // The deployment form is carried as a field; there is no per-form op branch.
    expect(code).toMatch(/deploymentForm:\s*input\.mode\.deploymentForm/);
  });

  it("the screen emits start_rollout from exactly one gated site", () => {
    const code = codeOf("screen.tsx");
    // Exactly one call to the single builder — a second call site would be a second start
    // path, the very thing CG-G-S11e forbids.
    const emits = [...code.matchAll(/buildStartRollout\(/g)];
    expect(emits.length).toBe(1);
    // That sole emitter guards on canStart before it sends (guard precedes the emit).
    expect(code).toMatch(/if\s*\(!canStart[\s\S]*?return[\s\S]*?buildStartRollout\(/);
  });
});

describe("CG-G-S11a: the screen locks every control on a schema mismatch", () => {
  it("composes the schema lock and disables the control panels with it", () => {
    const code = codeOf("screen.tsx");
    expect(code).toMatch(/controlLockReasons/);
    expect(code).toMatch(/const\s+locked\s*=/);
    // Each control-bearing panel receives the lock as its disabled state.
    expect(code).toMatch(/<ModeSelectorView[\s\S]*?disabled=\{locked\}/);
    expect(code).toMatch(/<TaskSwitcherView[\s\S]*?disabled=\{locked\}/);
    expect(code).toMatch(/<TakeoverControlView[\s\S]*?disabled=\{locked\}/);
  });
});

describe("facade / invariant I-2: no socket, no reconnect, no stamp", () => {
  it("constructs no WebSocket and holds no reconnect path", () => {
    for (const file of SHIPPED_FILES) {
      const code = codeOf(file);
      expect(code, `${file} must not open a socket`).not.toMatch(/\bWebSocket\b/);
      expect(code, `${file} must hold no reconnect path`).not.toMatch(
        /\breconnect\b|\bdisconnect\b|\bconnect\s*\(|재연결/,
      );
    }
  });

  it("does not stamp a repo_id or read wall-clock in the browser", () => {
    for (const file of SHIPPED_FILES) {
      expect(codeOf(file), `${file} must not read wall-clock`).not.toMatch(
        /strftime|toISOString|Date\.now\s*\(|new\s+Date\s*\(/,
      );
    }
  });

  it("loads no external origin (air-gap, FR-GUI-008)", () => {
    for (const file of SHIPPED_FILES) {
      expect(codeOf(file), `${file} must reach no external URL`).not.toMatch(/https?:\/\//);
    }
  });
});
