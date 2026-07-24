// Static proofs the shipped S-08 source obeys the facade and dataset invariants.
// These are the CG-G-S08 guards a render test cannot prove absent, so they are
// scanned the way the sibling screens scan their structural rules. The scan reads the
// shipped modules only; *.test.* and the stylesheet are scaffolding and excluded.
// Comments are stripped first, so these headers — which necessarily spell out the very
// words the scans forbid (observation.effort, wall-clock, export/convert, in-place) —
// are never themselves hits.
//
//   - CG-G-S08a: the channel plot resolves observation.state by the info.json `names`
//     index — no fixed-index constant, no numeric indexing into the state/action rows.
//   - CG-G-S08b: no `observation.effort` reference (the key does not exist).
//   - CG-G-S08c: `timestamp` is never labelled wall-clock; the jitter path reads the
//     capture_ts sidecar and never the synthetic timestamp grid.
//   - CG-G-S08e: no export / convert / import / hub-upload command op or UI action.
//   - CG-G-S08f: the only edit op is copy-on-write to a new repo_id — no in-place op.
//   - CG-G-S08g: axis labels carry the per-channel unit (.pos=deg/.vel=deg/s/.torque=Nm).
//   - facade / I-2: no repo_id stamping, no socket, no reconnect in the browser.

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

// The code of a file with comments removed. The rules bind the code, not the prose
// that documents them. The `:` guard keeps `https://` in a string from being eaten.
function codeOf(file: string): string {
  return shipped(file)
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

describe("CG-G-S08a: channel plot resolves by names index, no fixed index", () => {
  // A per-channel column index frozen into a constant — the exact defect the toggle
  // between 24-dim and 8-dim state would silently scramble. Two forms: an UPPER_SNAKE
  // constant and a camelCase field, each naming a channel AND a column word (index /
  // idx / slot / col / column) and assigned a literal integer. Two lookaheads let the
  // channel word and the column word appear in either order without the leading class
  // eating the channel keyword.
  const FIXED_INDEX_CONSTANTS: RegExp[] = [
    /\b(?=[A-Z0-9_]*(?:POS|VEL|TORQUE|STATE|CHANNEL|JOINT|GRIPPER))(?=[A-Z0-9_]*(?:INDEX|IDX|SLOT|COL|COLUMN))[A-Z][A-Z0-9_]*\s*[:=]\s*\d+/,
    /\b(?=[A-Za-z0-9_]*(?:[Pp]os|[Vv]el|[Tt]orque|[Cc]hannel|[Ss]tate|[Gg]ripper|[Jj]oint))(?=[A-Za-z0-9_]*(?:Index|Idx|Slot|Col|Column))[a-z][A-Za-z0-9_]*\s*[:=]\s*\d+/,
  ];

  // A numeric literal indexing into a state/action row: state[frame][0] / action[f][2].
  const NUMERIC_ROW_INDEX = /\b(?:state|action)\s*\[[^\]]+\]\s*\[\s*\d+\s*\]/;

  it("names no fixed per-channel index constant", () => {
    for (const file of SHIPPED_FILES) {
      for (const pattern of FIXED_INDEX_CONSTANTS) {
        expect(codeOf(file), `${file} must not freeze a channel index`).not.toMatch(pattern);
      }
    }
  });

  it("never indexes a state/action row by a numeric literal", () => {
    for (const file of SHIPPED_FILES) {
      expect(codeOf(file), `${file} must not index a row by a literal column`).not.toMatch(
        NUMERIC_ROW_INDEX,
      );
    }
  });

  it("resolves the channel by name (indexOf) in channels.ts and the plot", () => {
    expect(codeOf("channels.ts")).toMatch(/stateNames\.indexOf\(/);
    expect(codeOf("ChannelPlotView.tsx")).toMatch(/resolveStateChannel\(/);
  });
});

describe("CG-G-S08b: observation.effort does not exist", () => {
  it("references neither observation.effort nor a bare effort field", () => {
    for (const file of SHIPPED_FILES) {
      const code = codeOf(file);
      expect(code, `${file} must not name observation.effort`).not.toMatch(/observation\.effort/);
      expect(code, `${file} must not name an effort channel`).not.toMatch(/\beffort\b/i);
    }
  });
});

describe("CG-G-S08c: timestamp is synthetic, jitter reads capture_ts", () => {
  it("never presents the timestamp as wall-clock time", () => {
    for (const file of SHIPPED_FILES) {
      const code = codeOf(file);
      // Asserting the axis IS wall clock is the violation; `isWallClock: false` — the
      // honest declaration that it is NOT — is required and must not trip this. The
      // \b before `wall` excludes the isWallClock identifier (no word boundary after
      // "is") while still catching a standalone "wall-clock" / "wallclock" label.
      expect(code, `${file} must not assert wall-clock`).not.toMatch(/isWallClock:\s*true/);
      expect(code, `${file} must not label it wall-clock`).not.toMatch(/\bwall.?clock\b/i);
      expect(code, `${file} must not call it real/clock time`).not.toMatch(/벽시계|실제\s*시각/);
    }
  });

  it("carries the synthetic grid fact as isWallClock: false", () => {
    expect(codeOf("types.ts")).toMatch(/isWallClock:\s*false/);
  });

  it("computes jitter from the capture_ts sidecar, not the timestamp grid", () => {
    const jitter = codeOf("jitter.ts");
    expect(jitter).toMatch(/captureTsNs/);
    // The synthetic timestamp grid must never enter the jitter computation.
    expect(jitter, "jitter.ts must not read the synthetic timestamp").not.toMatch(/\btimestamp\b/);
    expect(codeOf("CaptureJitterView.tsx")).toMatch(/capture_?ts/i);
  });
});

describe("CG-G-S08e: no export / convert / import UI path", () => {
  const EXPORT_OP = /op:\s*["'][^"']*(?:export|convert|import|hub|upload|download)/i;
  const EXPORT_ACTION = /data-(?:action|testid)=["'][^"']*(?:export|convert|import)/i;
  const EXPORT_LABEL = /내보내기|포맷\s*변환/;

  it("declares no export/convert/import command op", () => {
    for (const file of SHIPPED_FILES) {
      expect(codeOf(file), `${file} must declare no export op`).not.toMatch(EXPORT_OP);
    }
  });

  it("exposes no export/convert action or label", () => {
    for (const file of SHIPPED_FILES) {
      const code = codeOf(file);
      expect(code, `${file} must expose no export action`).not.toMatch(EXPORT_ACTION);
      expect(code, `${file} must expose no export label`).not.toMatch(EXPORT_LABEL);
    }
  });
});

describe("CG-G-S08f: edit is copy-on-write only, no in-place path", () => {
  it("declares exactly one edit op, and it is cow_edit carrying an outputRepoId", () => {
    const commands = codeOf("commands.ts");
    const ops = [...commands.matchAll(/\bop:\s*"([^"]+)"/g)].map((m) => m[1]);
    expect(ops).toContain("cow_edit");
    // The cow_edit command interface names the new-dataset target.
    expect(commands).toMatch(/interface CowEditCommand[\s\S]*?outputRepoId:\s*string/);
  });

  it("names no in-place or overwrite edit op", () => {
    for (const file of SHIPPED_FILES) {
      const ops = [...codeOf(file).matchAll(/\bop:\s*["']([^"']+)["']/g)].map((m) => m[1]);
      for (const op of ops) {
        expect(op, `op ${op} must not be an in-place edit`).not.toMatch(/in.?place|overwrite/i);
      }
    }
  });

  it("sends the cow_edit intent with the backend output repo_id", () => {
    expect(codeOf("screen.tsx")).toMatch(/op:\s*"cow_edit"[\s\S]*?outputRepoId/);
  });
});

describe("CG-G-S08g: per-channel unit axis labels", () => {
  it("defines the three CTR-REC units and annotates each axis with its unit", () => {
    const channels = codeOf("channels.ts");
    expect(channels).toMatch(/"deg"/);
    expect(channels).toMatch(/"deg\/s"/);
    expect(channels).toMatch(/"Nm"/);
    expect(channels).toMatch(/function axisLabel/);
    expect(channels).toMatch(/unitForChannel\(/);
    expect(codeOf("ChannelPlotView.tsx")).toMatch(/axisLabel\(/);
  });
});

describe("facade / invariant I-2: no stamping, no socket, no reconnect", () => {
  it("does not stamp a repo_id or read wall-clock in the browser", () => {
    for (const file of SHIPPED_FILES) {
      expect(codeOf(file), `${file} must not stamp a repo_id`).not.toMatch(
        /stamp_repo_id\s*\(|strftime|toISOString|Date\.now\s*\(|new\s+Date\s*\(/,
      );
    }
  });

  it("constructs no WebSocket and holds no reconnect path", () => {
    for (const file of SHIPPED_FILES) {
      const code = codeOf(file);
      expect(code, `${file} must not open a socket`).not.toMatch(/\bWebSocket\b/);
      expect(code, `${file} must hold no reconnect path`).not.toMatch(
        /\breconnect\b|\bdisconnect\b|\bconnect\s*\(|재연결/,
      );
    }
  });
});
