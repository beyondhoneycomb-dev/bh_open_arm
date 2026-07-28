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
//   - NORM-009: the threshold wording names the residual. What the ruling
//     demands is a property of the string's CONTENT, which a scan for the
//     constant's own identifier cannot see, so the shipped strings are imported
//     and their clauses are read — what each one affirms as the comparison
//     target, and what it denies. Keyword presence is not enough: an inverted
//     sentence carries exactly the same words as the correct one.
//
// A further scan enforces the facade's unit discipline (no deg<->rad conversion
// in the browser — CTR-UNIT is the backend's), mirroring CG-G-02a.

import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, extname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  EFFORT_LIMIT_READOUT_LABEL,
  RESIDUAL_COMPARISON_NOTICE,
  THRESHOLD_READOUT_LABEL,
} from "./constants";

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

describe("NORM-009: the threshold readout names the residual as the comparison target", () => {
  const THRESHOLD_READOUT_MARKER = 'data-readout="threshold"';

  // A threshold number reaches the operator only out of a rendering file, so the
  // notice requirement is scanned over every one of them. Keying on the
  // data-readout marker instead makes the check opt-in: a second readout that
  // simply omits the marker ships a bare threshold with nothing to read it by.
  const RENDERING_EXTENSION = ".tsx";
  const THRESHOLD_ON_SCREEN: RegExp[] = [/threshold/i, /임계/];
  const NOTICE_RENDERED = /\{\s*RESIDUAL_COMPARISON_NOTICE\s*\}/;

  // The ruling's claim has two halves and the operator needs both: what the
  // threshold is measured against, and what it is not. The misreading it exists
  // to stop — "4.0 Nm means the arm stops at 4 of the 40 Nm the motor can make" —
  // survives a notice that names the residual without disowning the total torque,
  // and it survives a sentence that swaps the two, because an inversion keeps
  // every keyword. So the notice is read clause by clause: which quantity each
  // clause affirms as the comparison target, and which it denies.
  //
  // A clause ends at a sentence-final period followed by whitespace — "v2.0"
  // stays whole — or at the em dash the notice attaches a denial with.
  const CLAUSE_BOUNDARY = /\s*—\s*|\.\s+/;
  const COMPARISON_VERB = /비교/;
  // Captures the noun the comparison particle attaches to — what the notice puts
  // on the other side of the comparison. A clause that compares while capturing
  // nothing names no target at all, which the checks below treat as a failure.
  const COMPARISON_TARGET = /(\S+?)\s*(?:와|과)\s*비교/g;
  const RESIDUAL_NAMED = /잔차/;
  const TOTAL_TORQUE_NAMED = /총\s*토크/;
  // Negation endings the notice rules a reading out with. Korean composes each
  // syllable into one glyph, so the polite and the connective form of the same
  // verb share no prefix and both have to be listed.
  const NEGATED = /않|아닙|아니/;
  const EFFORT_LIMIT_DISOWNED = /비교\s*대상\s*아님/;

  // FR-SAF-030 (12 §3.4) forces detection DISABLED because a residual computed
  // from an unidentified friction model false-triggers and false-misses, and the
  // shipped default source reports PG-FRIC-001 not passed — DetectionPanel holds
  // that banner on screen beside this notice (screen.test.tsx pins it). The
  // caveat is owed in that state whatever words describe the residual's resting
  // behaviour, so the check is unconditional; triggering it on the near-zero
  // phrasing lets a single paraphrase drop the promise and the caveat together.
  const UNIDENTIFIED_FRICTION_CAVEAT = /마찰\s*모델[^.]*식별/;
  const FORCED_DISABLE_CITATION = /FR-SAF-030|PG-FRIC-001/;

  function clausesOf(notice: string): string[] {
    return notice
      .split(CLAUSE_BOUNDARY)
      .map((clause) => clause.trim())
      .filter((clause) => clause.length > 0);
  }

  function comparisonTargetsOf(clause: string): string[] {
    return Array.from(clause.matchAll(COMPARISON_TARGET), (match) => match[1]);
  }

  const NOTICE_CLAUSES = clausesOf(RESIDUAL_COMPARISON_NOTICE);
  const AFFIRMED_COMPARISONS = NOTICE_CLAUSES.filter(
    (clause) => COMPARISON_VERB.test(clause) && !NEGATED.test(clause),
  );
  const DENIED_COMPARISONS = NOTICE_CLAUSES.filter(
    (clause) => COMPARISON_VERB.test(clause) && NEGATED.test(clause),
  );

  it("renders the comparison notice in every screen file that puts a threshold on screen", () => {
    const offenders: string[] = [];
    for (const { path, code } of SOURCES) {
      if (extname(path) !== RENDERING_EXTENSION) {
        continue;
      }
      if (!THRESHOLD_ON_SCREEN.some((pattern) => pattern.test(code))) {
        continue;
      }
      if (!NOTICE_RENDERED.test(code)) {
        offenders.push(path);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("keeps the threshold readout in exactly one file (ResidualPlot)", () => {
    const withReadout = SOURCES.filter(({ code }) => code.includes(THRESHOLD_READOUT_MARKER));
    expect(withReadout).toHaveLength(1);
    expect(withReadout[0].path.endsWith("ResidualPlot.tsx")).toBe(true);
  });

  it("names the residual, and nothing else, as what the threshold is compared to", () => {
    const offenders = AFFIRMED_COMPARISONS.filter((clause) => {
      const targets = comparisonTargetsOf(clause);
      return targets.length === 0 || targets.some((target) => !RESIDUAL_NAMED.test(target));
    });
    expect(offenders).toEqual([]);
    const residualAffirmed = AFFIRMED_COMPARISONS.filter((clause) =>
      comparisonTargetsOf(clause).some((target) => RESIDUAL_NAMED.test(target)),
    );
    expect(residualAffirmed.length).toBeGreaterThan(0);
  });

  it("never states the residual comparison in the negative", () => {
    const offenders = DENIED_COMPARISONS.filter((clause) =>
      comparisonTargetsOf(clause).some((target) => RESIDUAL_NAMED.test(target)),
    );
    expect(offenders).toEqual([]);
  });

  it("names the total motor torque only to rule it out", () => {
    const mentions = NOTICE_CLAUSES.filter((clause) => TOTAL_TORQUE_NAMED.test(clause));
    expect(mentions.filter((clause) => !NEGATED.test(clause))).toEqual([]);
    expect(mentions.length).toBeGreaterThan(0);
  });

  it("names the residual in the threshold label and never the total torque", () => {
    expect(THRESHOLD_READOUT_LABEL).toMatch(RESIDUAL_NAMED);
    expect(THRESHOLD_READOUT_LABEL).not.toMatch(TOTAL_TORQUE_NAMED);
  });

  it("keeps the effort limit labelled as something the threshold is not compared to", () => {
    expect(EFFORT_LIMIT_READOUT_LABEL).toMatch(EFFORT_LIMIT_DISOWNED);
  });

  it("qualifies the residual's resting behaviour with the unidentified friction model", () => {
    expect(RESIDUAL_COMPARISON_NOTICE).toMatch(UNIDENTIFIED_FRICTION_CAVEAT);
    expect(RESIDUAL_COMPARISON_NOTICE).toMatch(FORCED_DISABLE_CITATION);
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
