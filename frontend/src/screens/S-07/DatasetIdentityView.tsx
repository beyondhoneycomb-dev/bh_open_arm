// The dataset name panel (CG-G-S07b). The name shown as THE dataset is always the
// backend-stamped repo_id — the output of `stamp_repo_id()` (WP-3B-11 ⑤) — never
// the operator's raw input. The raw request is shown only as context, explicitly
// labelled as the request and paired with the stamped result, so it can never be
// mistaken for the name display, save target, or Resume key. The screen computes no
// stamp; it renders the field the backend supplies.

import type { DatasetIdentity } from "./types";

export interface DatasetIdentityViewProps {
  dataset: DatasetIdentity;
}

export function DatasetIdentityView({ dataset }: DatasetIdentityViewProps) {
  const stamped = dataset.requestedRepoId !== dataset.stampedRepoId;
  return (
    <section className="oa-collect__dataset" aria-labelledby="oa-collect-dataset-title">
      <h2 id="oa-collect-dataset-title" className="oa-collect__section-title">
        데이터셋
      </h2>
      <p className="oa-collect__dataset-name" data-testid="dataset-name">
        <span className="oa-collect__dataset-label">이름</span>
        <code className="oa-collect__dataset-id">{dataset.stampedRepoId}</code>
      </p>
      {stamped && (
        <p className="oa-collect__dataset-request" data-testid="dataset-request">
          요청 <code>{dataset.requestedRepoId}</code> → 스탬프 부착됨
        </p>
      )}
    </section>
  );
}
