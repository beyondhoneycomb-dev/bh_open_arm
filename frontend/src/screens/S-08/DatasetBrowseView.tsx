// The dataset browse list (WP-3D-01 viewer / WP-3D-04 lineage). Each row is one
// dataset the backend inventoried, keyed by its stamped repo_id and content hash. The
// `use_velocity_and_torque` badge makes the state-vector family (24-dim pos+vel+torque
// vs 8-dim pos-only) visible, because that toggle is what moves every channel's column
// — the reason the plot resolves by name, never by a fixed index (CG-G-S08a).

import type { DatasetSummary } from "./types";

export interface DatasetBrowseViewProps {
  datasets: readonly DatasetSummary[];
  selectedRepoId: string;
  onSelect: (stampedRepoId: string) => void;
}

export function DatasetBrowseView({ datasets, selectedRepoId, onSelect }: DatasetBrowseViewProps) {
  return (
    <section className="oa-ds__browse" aria-labelledby="oa-ds-browse-title">
      <h2 id="oa-ds-browse-title" className="oa-ds__section-title">
        데이터셋 목록
      </h2>
      <ul className="oa-ds__browse-list">
        {datasets.map((dataset) => {
          const selected = dataset.stampedRepoId === selectedRepoId;
          return (
            <li key={dataset.stampedRepoId}>
              <button
                type="button"
                className="oa-ds__browse-row"
                aria-pressed={selected}
                data-selected={selected}
                data-testid={`dataset-${dataset.stampedRepoId}`}
                onClick={() => onSelect(dataset.stampedRepoId)}
              >
                <span className="oa-ds__browse-name">{dataset.stampedRepoId}</span>
                <span className="oa-ds__browse-meta">
                  <span>{dataset.totalEpisodes} 에피소드</span>
                  <span>{dataset.totalFrames} 프레임</span>
                  <span>state {dataset.stateDim}D</span>
                  <span
                    className="oa-ds__vt-badge"
                    data-vt={dataset.useVelocityAndTorque}
                    title="use_velocity_and_torque"
                  >
                    {dataset.useVelocityAndTorque ? "pos+vel+torque" : "pos only"}
                  </span>
                </span>
                <span className="oa-ds__browse-hash">
                  {dataset.contentHash} · {dataset.revision}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
