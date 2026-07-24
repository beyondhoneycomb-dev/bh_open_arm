// Static proofs the shipped S-10 source obeys the facade and training invariants.
// These are the CG-G-S10 / CG-4A-G1 guards a render test cannot prove absent, so they
// are scanned the way the sibling screens scan their structural rules. The scan reads
// the shipped .ts/.tsx modules only; *.test.*, the stylesheet and the .json snapshot are
// excluded — the snapshot is DATA (the registry response stand-in), not code, which is
// the whole point of CG-4A-G1a: policy names live in data, never in the UI code.
// Comments are stripped first, so these headers — which necessarily spell out the very
// tokens the scans forbid — are never themselves hits.
//
//   - CG-4A-G1a: no hardcoded policy name string in the code; the list is runtime-
//     derived from the registry snapshot (policyRegistry.ts).
//   - CG-4A-G1b: the chart key set is exactly MetricsTracker's seven outputs — no
//     invented key in metrics.ts.
//   - CG-G-S10f: no command op carries a multi-dataset list; a job trains on one dataset.
//   - CG-G-S10 ⑤: `create_job` is the only start op, and it is emitted only past the gate.
//   - facade / I-2: no socket, no reconnect, no browser-side repo_id stamp.

import { readFileSync, readdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { METRIC_KEYS } from "./metrics";

const HERE = dirname(fileURLToPath(import.meta.url));

const SHIPPED_FILES = readdirSync(HERE).filter(
  (name) => /\.(ts|tsx)$/.test(name) && !name.includes(".test."),
);

function shipped(file: string): string {
  return readFileSync(resolve(HERE, file), "utf-8");
}

// The code of a file with comments removed. The rules bind the code, not the prose that
// documents them. The `:` guard keeps `https://` and `./x.json?raw` paths intact.
function codeOf(file: string): string {
  return shipped(file)
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

interface SnapshotShape {
  policies: { id: string }[];
}

function snapshotPolicyIds(): string[] {
  const raw = readFileSync(resolve(HERE, "policyRegistrySnapshot.json"), "utf-8");
  const parsed = JSON.parse(raw) as SnapshotShape;
  return parsed.policies.map((policy) => policy.id);
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

describe("CG-4A-G1a: policy list is runtime-derived, no hardcoded policy name", () => {
  // The denylist is derived from the snapshot itself (the exact ids the UI renders),
  // plus a fixed set of well-known lerobot ids so the check bites even if the snapshot
  // is trimmed. A policy id appearing as a BARE quoted string literal is the hardcode
  // this forbids — that is how a stale UI list would be written.
  const WELL_KNOWN = ["smolvla", "pi0", "pi05", "groot", "act", "diffusion", "vqbet", "tdmpc"];
  const DENY = [...new Set([...snapshotPolicyIds(), ...WELL_KNOWN])];

  it("names at least one policy in the snapshot (non-vacuous)", () => {
    expect(snapshotPolicyIds().length).toBeGreaterThan(0);
  });

  it("no shipped .ts/.tsx contains a policy id as a bare quoted string literal", () => {
    for (const file of SHIPPED_FILES) {
      const code = codeOf(file);
      for (const id of DENY) {
        const pattern = new RegExp(`(["'\`])${escapeRegExp(id)}\\1`);
        expect(code, `${file} must not hardcode policy id ${id}`).not.toMatch(pattern);
      }
    }
  });

  it("the snapshot is imported as data (raw json), so its names never enter code", () => {
    expect(codeOf("policyRegistry.ts")).toMatch(/policyRegistrySnapshot\.json\?raw/);
  });
});

describe("CG-4A-G1b: chart keys are exactly MetricsTracker's seven outputs", () => {
  // The contract set, restated here as the acceptance authority (lerobot 0.6.0
  // lerobot/scripts/lerobot_train.py). METRIC_KEYS must equal this and nothing more.
  const METRICS_TRACKER_OUTPUTS = [
    "loss",
    "grad_norm",
    "lr",
    "samples_per_s",
    "update_s",
    "dataloading_s",
    "gpu_mem_gb",
  ];

  it("metrics.ts declares exactly the seven keys, no invented key", () => {
    expect([...METRIC_KEYS].sort()).toEqual([...METRICS_TRACKER_OUTPUTS].sort());
  });

  it("the chart guards every series through isMetricKey", () => {
    expect(codeOf("LossCurveView.tsx")).toMatch(/isMetricKey\(/);
  });
});

describe("CG-G-S10f: no multi-dataset list UI or command", () => {
  it("the select-dataset command carries a single repo_id, never a list", () => {
    const commands = codeOf("commands.ts");
    expect(commands).toMatch(/interface SelectDatasetCommand[\s\S]*?datasetRepoId:\s*string/);
    // No plural array form of the dataset axis anywhere in the op set.
    for (const file of SHIPPED_FILES) {
      expect(codeOf(file), `${file} must not name a dataset list`).not.toMatch(
        /datasetRepoIds\b|datasetRepoId:\s*(?:readonly\s+)?string\[\]|datasets:\s*string\[\]/,
      );
    }
  });
});

describe("CG-G-S10 ⑤: create_job is the only start op", () => {
  it("declares exactly one create/start op, and it is create_job", () => {
    const ops = [...codeOf("commands.ts").matchAll(/\bop:\s*"([^"]+)"/g)].map((m) => m[1]);
    const starters = ops.filter((op) => /create|start|launch|train/i.test(op));
    expect(starters).toEqual(["create_job"]);
  });

  it("the screen emits create_job from exactly one gated site", () => {
    const code = codeOf("screen.tsx");
    expect(code).toMatch(/canStartTraining|canStart/);
    // There must be exactly ONE create_job emit site. A second call site — e.g. an
    // ungated checkpoint-resume — is precisely the bypass CG-G-S10 ⑤ forbids, so more
    // than one emit fails here (a "contains one guard" check would miss the second site).
    const emits = [...code.matchAll(/op:\s*"create_job"/g)];
    expect(emits.length).toBe(1);
    // That sole emitter guards on the gate before it sends (guard precedes the emit).
    expect(code).toMatch(/if\s*\(!canStart[\s\S]*?return[\s\S]*?op:\s*"create_job"/);
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
      expect(codeOf(file), `${file} must not stamp a repo_id`).not.toMatch(
        /stamp_repo_id\s*\(|strftime|toISOString|Date\.now\s*\(|new\s+Date\s*\(/,
      );
    }
  });
});
