// The dataset selector + statistics + VRAM preflight (FR-GUI-122/123, CG-G-S10e/f). A
// job trains on ONE dataset: the selector is single-choice (a radio list), there is no
// multi-dataset list control, and the screen points at the dataset screen (S-08) for the
// merge path instead (CG-G-S10f). A dataset under the 50-episode floor shows a warning
// (small data trains, it just generalises poorly) — a warning, never a block. The VRAM
// preflight shows required vs. available with the SOURCE of the estimate; when it does
// not fit, the alternatives are listed and the start is disabled upstream (CG-G-S10e).

import type { DatasetOption, VramPreflight } from "./types";

// FR-GUI-122 small-dataset floor: below this episode count the form warns.
export const DATASET_MIN_EPISODES = 50;

export interface DatasetFormViewProps {
  datasets: readonly DatasetOption[];
  selectedRepoId: string;
  vram: VramPreflight;
  onSelectDataset: (repoId: string) => void;
}

export function DatasetFormView({
  datasets,
  selectedRepoId,
  vram,
  onSelectDataset,
}: DatasetFormViewProps) {
  return (
    <section className="oa-trn__panel" aria-labelledby="oa-trn-dataset-title" data-testid="dataset-form">
      <h2 id="oa-trn-dataset-title" className="oa-trn__section-title">
        데이터셋 선택 + 통계
      </h2>

      <ul className="oa-trn__dataset-list" role="radiogroup" aria-label="데이터셋">
        {datasets.map((dataset) => {
          const selected = dataset.repoId === selectedRepoId;
          const belowFloor = dataset.episodeCount < DATASET_MIN_EPISODES;
          return (
            <li key={dataset.repoId} className="oa-trn__dataset-item">
              <label className="oa-trn__dataset-label" data-testid={`dataset-${dataset.repoId}`}>
                <input
                  type="radio"
                  name="oa-trn-dataset"
                  value={dataset.repoId}
                  checked={selected}
                  data-testid={`dataset-radio-${dataset.repoId}`}
                  onChange={() => onSelectDataset(dataset.repoId)}
                />
                <span className="oa-trn__dataset-name">{dataset.repoId}</span>
                <span className="oa-trn__muted"> · {dataset.revision}</span>
              </label>
              <p className="oa-trn__dataset-stats" data-testid={`dataset-stats-${dataset.repoId}`}>
                에피소드 {dataset.episodeCount} · 프레임 {dataset.frameCount} · state {dataset.stateDim}차원
                {dataset.useVelocityAndTorque ? " (pos+vel+torque)" : " (pos-only)"} · {dataset.sizeGb} GB
              </p>
              {belowFloor && (
                <p className="oa-trn__warn" data-testid={`dataset-warn-${dataset.repoId}`}>
                  에피소드 {dataset.episodeCount}개 (&lt; {DATASET_MIN_EPISODES}) — 일반화가 어려울 수 있습니다
                </p>
              )}
            </li>
          );
        })}
      </ul>

      <p className="oa-trn__merge-note" data-testid="merge-note">
        여러 데이터셋을 함께 학습하려면 데이터셋 화면(S-08)에서 먼저 병합한 뒤 단일 데이터셋으로 선택하세요.
      </p>

      <div className="oa-trn__vram" data-testid="vram-preflight" data-fits={vram.fits}>
        <h3 className="oa-trn__subhead">VRAM 사전검증</h3>
        <p data-testid="vram-figures">
          필요 {vram.requiredGb} GB / 가용 {vram.availableGb} GB — {vram.fits ? "충족" : "부족"}
        </p>
        <p className="oa-trn__source" data-testid="vram-source">
          출처: {vram.source}
        </p>
        {!vram.fits && vram.alternatives.length > 0 && (
          <ul className="oa-trn__alternatives" data-testid="vram-alternatives">
            {vram.alternatives.map((alternative) => (
              <li key={alternative}>{alternative}</li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
