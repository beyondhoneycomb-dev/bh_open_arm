// Static scans over the S-06 production source (every non-test .ts/.tsx under
// this screen). Three gates are structural invariants a render test cannot prove
// absent, so they are scanned the way the safety screen's static checks scan for
// collision primitives:
//
//   - CG-G-S06a: no hardcoded tile-count constant. The tile set is derived from
//     `observation_features`; a compiled-in count would silently mis-render when
//     the camera configuration changes.
//   - CG-G-S06f: no single-method hand-eye adoption. The screen must render all
//     five methods and never collapse them to one "answer" (FR-CAM-026).
//   - facade unit discipline: no deg<->rad conversion in the browser (CTR-UNIT is
//     the backend's), mirroring CG-G-02a.

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

// Strip comments so the prose in this screen (which necessarily discusses tile
// counts, method adoption and units) never trips the code scans. Mirrors
// global/staticChecks and the S-12 screen scan.
function stripComments(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(?<!:)\/\/.*$/gm, "");
}

const SOURCES = collectSources(SCREEN_ROOT, []).map((path) => ({
  path,
  code: stripComments(readFileSync(path, "utf-8")),
}));

describe("CG-G-S06a: no hardcoded tile-count constant", () => {
  // A numeric literal bound to anything that reads as a tile/camera count. The
  // tile set is derived, so any such constant is the defect.
  const TILE_COUNT_CONSTANTS: RegExp[] = [
    /\b(?:TILE_COUNT|NUM_TILES|CAMERA_COUNT|MAX_TILES|TILES_PER_ROW|GRID_COLUMNS)\b/,
    /\b(?:tile|camera)[A-Za-z]*[Cc]ount\s*[:=]\s*\d+/,
    /\bcount(?:Of)?(?:Tiles|Cameras)\b\s*[:=]\s*\d+/,
  ];

  it("names no tile-count constant anywhere in the screen source", () => {
    const offenders: string[] = [];
    for (const { path, code } of SOURCES) {
      for (const pattern of TILE_COUNT_CONSTANTS) {
        if (pattern.test(code)) {
          offenders.push(`${path}: ${pattern}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("derives the tile set through deriveTiles in the grid", () => {
    const grid = SOURCES.find(({ path }) => path.endsWith("TilePreviewGrid.tsx"));
    expect(grid).toBeDefined();
    expect(grid?.code).toMatch(/deriveTiles\(/);
  });
});

describe("CG-G-S06f: no single-method hand-eye adoption", () => {
  const SINGLE_METHOD_ADOPT: RegExp[] = [
    /\badopt\w*Method\b/i,
    /\bchosenMethod\b/i,
    /\bselectedMethod\b/i,
    /\bbestMethod\b/i,
    /\bpickMethod\b/i,
    /data-action="adopt-method"/,
    /\.methods\s*\[\s*0\s*\]/,
    /\.solutions\s*\[\s*0\s*\]/,
  ];

  it("names no single-method-adopt accessor or control", () => {
    const offenders: string[] = [];
    for (const { path, code } of SOURCES) {
      for (const pattern of SINGLE_METHOD_ADOPT) {
        if (pattern.test(code)) {
          offenders.push(`${path}: ${pattern}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("renders the full method set in the compare view", () => {
    const view = SOURCES.find(({ path }) => path.endsWith("HandEyeCompareView.tsx"));
    expect(view).toBeDefined();
    expect(view?.code).toMatch(/view\.methods\.map/);
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
