// Static scans over the S-12 production source (every non-test .ts/.tsx under
// this screen). Two gates are structural invariants a render test cannot prove
// absent, so they are checked by scanning the source the way the viewport's
// static checks scan for deg<->rad conversion:
//
//   - CG-G-S12d: zero self-collision decision. The screen must contain no
//     collision-detection primitive — the judgement is entirely the backend's,
//     and a wall edit reaches the scene only through the geom injector.
//   - CG-G-S12b: the enable-detection control exists only behind the gate. Any
//     file that renders the enable action must also gate it on enableAllowed.
//
// A third scan enforces the facade's unit discipline (no deg<->rad conversion in
// the browser — CTR-UNIT is the backend's), mirroring CG-G-02a.

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
      collectSources(full, acc);
    } else if (SCANNED_EXTENSIONS.has(extname(full)) && !isTestFile(full)) {
      acc.push(full);
    }
  }
  return acc;
}

// Strip comments so the heavy prose in this screen (which necessarily discusses
// collision and units) never trips the code scans. Mirrors global/staticChecks.
function stripComments(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(?<!:)\/\/.*$/gm, "");
}

const SOURCES = collectSources(SCREEN_ROOT, []).map((path) => ({
  path,
  code: stripComments(readFileSync(path, "utf-8")),
}));

describe("CG-G-S12d: zero self-collision decision in the GUI", () => {
  // Primitives a browser-side collision judgement would need. The screen has none
  // — MuJoCo decides contacts in the backend and reports them (§2.11).
  const COLLISION_PRIMITIVES: RegExp[] = [
    /detectCollision/i,
    /checkCollision/i,
    /isColliding/i,
    /computeCollision/i,
    /\bcollide\b/i,
    /\bintersect/i,
    /raycast/i,
    /penetrationDepth/i,
    /boundingBox/i,
    /\bAABB\b/,
  ];

  it("names no collision-detection primitive anywhere in the screen source", () => {
    const offenders: string[] = [];
    for (const { path, code } of SOURCES) {
      for (const pattern of COLLISION_PRIMITIVES) {
        if (pattern.test(code)) {
          offenders.push(`${path}: ${pattern}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("routes wall edits only through the geom injector callbacks", () => {
    const editor = SOURCES.find(({ path }) => path.endsWith("VirtualWallEditor.tsx"));
    expect(editor).toBeDefined();
    const code = editor?.code ?? "";
    // The only mutation paths a wall edit takes are the backend injector callbacks.
    expect(code).toMatch(/onInjectWall/);
    expect(code).toMatch(/onRemoveWall/);
  });
});

describe("CG-G-S12b: the enable-detection control exists only behind the gate", () => {
  it("gates every enable-detection action on enableAllowed", () => {
    for (const { code } of SOURCES) {
      if (code.includes('data-action="enable-detection"')) {
        expect(code).toMatch(/enableAllowed/);
      }
    }
  });

  it("keeps the enable action in exactly one gated file (DetectionPanel)", () => {
    const withEnable = SOURCES.filter(({ code }) =>
      code.includes('data-action="enable-detection"'),
    );
    expect(withEnable).toHaveLength(1);
    expect(withEnable[0].path.endsWith("DetectionPanel.tsx")).toBe(true);
  });
});

describe("facade unit discipline: no deg<->rad conversion in the browser (CTR-UNIT)", () => {
  const CONVERSION_PATTERNS: RegExp[] = [
    /Math\.PI\s*\/\s*180/,
    /180\s*\/\s*Math\.PI/,
    /\bdeg2rad\b/i,
    /\brad2deg\b/i,
    /RAD_PER_DEG/,
    /DEG_PER_RAD/,
    /setJointValue\s*\([^)]*deg/i,
  ];

  it("performs no degree/radian conversion in any screen source file", () => {
    const offenders: string[] = [];
    for (const { path, code } of SOURCES) {
      for (const pattern of CONVERSION_PATTERNS) {
        if (pattern.test(code)) {
          offenders.push(`${path}: ${pattern}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
