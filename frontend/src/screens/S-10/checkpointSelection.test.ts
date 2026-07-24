// CG-4A-G1d coverage: the default checkpoint is the latest, never the minimum val loss,
// and the "offline metrics do not predict online success" warning constant exists.

import { describe, expect, it } from "vitest";

import {
  OFFLINE_METRIC_WARNING,
  defaultCheckpoint,
  minValLossCheckpoint,
} from "./checkpointSelection";
import type { CheckpointEntry } from "./types";

const CHECKPOINTS: CheckpointEntry[] = [
  { step: 2000, path: "c/002000", savedIso: "t1", valLoss: 0.71, isLast: false },
  { step: 6000, path: "c/006000", savedIso: "t3", valLoss: 0.51, isLast: false },
  { step: 8000, path: "c/008000", savedIso: "t4", valLoss: 0.55, isLast: true },
];

describe("checkpoint default selection (CG-4A-G1d)", () => {
  it("defaults to the latest checkpoint (the `last` symlink target), not min val loss", () => {
    const chosen = defaultCheckpoint(CHECKPOINTS);
    expect(chosen?.step).toBe(8000);
    expect(chosen?.isLast).toBe(true);
  });

  it("the min-val-loss checkpoint is a DIFFERENT, non-latest step", () => {
    const min = minValLossCheckpoint(CHECKPOINTS);
    expect(min?.step).toBe(6000);
    expect(min?.step).not.toBe(defaultCheckpoint(CHECKPOINTS)?.step);
  });

  it("falls back to the highest step when no `last` symlink is present", () => {
    const noLast = CHECKPOINTS.map((c) => ({ ...c, isLast: false }));
    expect(defaultCheckpoint(noLast)?.step).toBe(8000);
  });

  it("returns null for an empty list", () => {
    expect(defaultCheckpoint([])).toBeNull();
    expect(minValLossCheckpoint([])).toBeNull();
  });

  it("always carries the offline-metric warning text", () => {
    expect(OFFLINE_METRIC_WARNING).toContain("온라인 성공률");
  });
});
