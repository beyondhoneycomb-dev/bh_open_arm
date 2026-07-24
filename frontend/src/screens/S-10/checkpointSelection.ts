// Checkpoint default-selection policy (CG-G-S10d / FR-GUI-125, FR-INF-062). The
// checkpoint list must NOT default to the minimum-val-loss checkpoint, and it must
// ALWAYS show the warning that offline metrics do not predict online success. The two
// rules are one idea: a lower val loss is not a better robot, so steering the operator
// toward it by default is a readable lie. The default here is the LATEST checkpoint
// (the most training the run has), which makes no success claim; the operator picks
// deliberately, warned.

import type { CheckpointEntry } from "./types";

// Shown next to the checkpoint list at all times (CG-G-S10d). Not dismissible: the
// warning is the point, and a warning you can turn off is a warning you will.
export const OFFLINE_METRIC_WARNING =
  "오프라인 지표(val loss 등)는 온라인 성공률을 예측하지 못합니다 — " +
  "가장 낮은 val loss가 가장 좋은 정책이라는 보장은 없습니다.";

// The default-selected checkpoint: the latest by step, never the minimum val loss. The
// trainer's atomic `checkpoints/last` symlink is preferred when present (it is what a
// resume points at); otherwise the highest step wins. Returns null for an empty list.
export function defaultCheckpoint(checkpoints: readonly CheckpointEntry[]): CheckpointEntry | null {
  if (checkpoints.length === 0) {
    return null;
  }
  const last = checkpoints.find((checkpoint) => checkpoint.isLast);
  if (last !== undefined) {
    return last;
  }
  return checkpoints.reduce((newest, candidate) =>
    candidate.step > newest.step ? candidate : newest,
  );
}

// The minimum-val-loss checkpoint, computed ONLY so the list can label it as such and
// explicitly NOT auto-select it — surfacing the tempting choice while refusing to make
// it (CG-G-S10d). Returns null when no checkpoint carries a val loss.
export function minValLossCheckpoint(
  checkpoints: readonly CheckpointEntry[],
): CheckpointEntry | null {
  const scored = checkpoints.filter((checkpoint) => checkpoint.valLoss !== null);
  if (scored.length === 0) {
    return null;
  }
  return scored.reduce((best, candidate) =>
    (candidate.valLoss as number) < (best.valLoss as number) ? candidate : best,
  );
}
