// The checkpoint list + resume (FR-GUI-125, CG-G-S10d). The default selection is the
// LATEST checkpoint, never the minimum-val-loss one, and the warning that offline
// metrics do not predict online success is shown at all times (checkpointSelection.ts
// owns both rules). The minimum-val-loss checkpoint is labelled as such precisely so it
// can be seen and NOT chosen by default — surfacing the tempting option while refusing
// to make it. Resume emits an intent carrying the checkpoint step; the backend performs
// the resume.

import { useState } from "react";

import {
  OFFLINE_METRIC_WARNING,
  defaultCheckpoint,
  minValLossCheckpoint,
} from "./checkpointSelection";
import type { CheckpointEntry } from "./types";

export interface CheckpointListViewProps {
  checkpoints: readonly CheckpointEntry[];
  onResume: (step: number) => void;
  // Resume starts a run, so it obeys the same start gate: the buttons are disabled
  // whenever the gate is not clear (CG-G-S10 ⑤). Defaults to false so a caller that
  // forgets to wire the gate cannot accidentally leave resume enabled.
  canResume?: boolean;
}

export function CheckpointListView({
  checkpoints,
  onResume,
  canResume = false,
}: CheckpointListViewProps) {
  const initial = defaultCheckpoint(checkpoints);
  const minValLoss = minValLossCheckpoint(checkpoints);
  const [selectedStep, setSelectedStep] = useState<number | null>(initial?.step ?? null);

  return (
    <section
      className="oa-trn__panel"
      aria-labelledby="oa-trn-checkpoints-title"
      data-testid="checkpoint-list"
      data-default-step={initial?.step ?? ""}
      data-min-valloss-step={minValLoss?.step ?? ""}
    >
      <h2 id="oa-trn-checkpoints-title" className="oa-trn__section-title">
        체크포인트 (중단/재개)
      </h2>

      <p className="oa-trn__warn oa-trn__warn--persistent" data-testid="offline-metric-warning">
        {OFFLINE_METRIC_WARNING}
      </p>

      <table className="oa-trn__ckpt-table">
        <thead>
          <tr>
            <th scope="col">선택</th>
            <th scope="col">스텝</th>
            <th scope="col">저장 시각</th>
            <th scope="col">val loss</th>
            <th scope="col">경로</th>
            <th scope="col">재개</th>
          </tr>
        </thead>
        <tbody>
          {checkpoints.map((checkpoint) => {
            const isSelected = checkpoint.step === selectedStep;
            const isMinValLoss = minValLoss?.step === checkpoint.step;
            return (
              <tr
                key={checkpoint.step}
                data-testid={`checkpoint-${checkpoint.step}`}
                data-selected={isSelected}
                data-is-last={checkpoint.isLast}
                data-is-min-valloss={isMinValLoss}
              >
                <td>
                  <input
                    type="radio"
                    name="oa-trn-ckpt"
                    checked={isSelected}
                    data-testid={`checkpoint-select-${checkpoint.step}`}
                    onChange={() => setSelectedStep(checkpoint.step)}
                  />
                </td>
                <td>
                  {checkpoint.step}
                  {checkpoint.isLast && <span className="oa-trn__badge"> last</span>}
                </td>
                <td>{checkpoint.savedIso}</td>
                <td>
                  {checkpoint.valLoss ?? "—"}
                  {isMinValLoss && (
                    <span className="oa-trn__muted" data-testid={`checkpoint-minvalloss-${checkpoint.step}`}>
                      {" "}
                      (val loss 최소 — 기본 선택 아님)
                    </span>
                  )}
                </td>
                <td className="oa-trn__muted">{checkpoint.path}</td>
                <td>
                  <button
                    type="button"
                    data-testid={`checkpoint-resume-${checkpoint.step}`}
                    disabled={!canResume}
                    onClick={() => onResume(checkpoint.step)}
                  >
                    재개
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
