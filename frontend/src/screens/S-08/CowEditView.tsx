// The copy-on-write edit view (CG-G-S08f). Every edit the screen offers writes to a
// NEW dataset the backend stamped (`outputRepoId`) and leaves the source immutable —
// there is no in-place path, no overwrite toggle, no path that names the source as its
// own output. Even an operation that is destructive upstream (modify_tasks mutates its
// input directory) is copied first by the backend engine, so the policy row shows that
// the original is preserved regardless. The view renders the backend's edit preview
// and emits the run intent; it never performs the transformation.

import type { EditPreview } from "./types";

export interface CowEditViewProps {
  preview: EditPreview | null;
  onRunEdit: (preview: EditPreview) => void;
}

export function CowEditView({ preview, onRunEdit }: CowEditViewProps) {
  return (
    <section className="oa-ds__edit" aria-labelledby="oa-ds-edit-title">
      <h2 id="oa-ds-edit-title" className="oa-ds__section-title">
        편집 (Copy-on-Write)
      </h2>

      {preview === null ? (
        <p className="oa-ds__edit-empty" data-testid="edit-empty">
          준비된 편집이 없습니다.
        </p>
      ) : (
        <div className="oa-ds__edit-card" data-testid="edit-preview">
          <dl className="oa-ds__edit-grid">
            <div className="oa-ds__edit-row">
              <dt>연산</dt>
              <dd data-testid="edit-operation">{preview.operation}</dd>
            </div>
            <div className="oa-ds__edit-row">
              <dt>원본</dt>
              <dd data-testid="edit-source">{preview.sourceRepoId}</dd>
            </div>
            <div className="oa-ds__edit-row">
              <dt>새 데이터셋 (결과)</dt>
              <dd data-testid="edit-output">{preview.outputRepoId}</dd>
            </div>
            <div className="oa-ds__edit-row">
              <dt>에피소드 재번호</dt>
              <dd>{preview.policy.renumbers ? "예 (사이드카 재매핑 검증)" : "아니오"}</dd>
            </div>
            <div className="oa-ds__edit-row">
              <dt>upstream in-place</dt>
              <dd data-testid="edit-inplace-policy">
                {preview.policy.inPlace ? "예 — 엔진이 먼저 복사" : "아니오"}
              </dd>
            </div>
          </dl>

          <p className="oa-ds__edit-summary">{preview.summary}</p>

          <p className="oa-ds__edit-cow-note" data-testid="edit-cow-note">
            원본은 보존됩니다 — 편집 결과는 새 데이터셋으로 기록됩니다.
          </p>

          <button
            type="button"
            className="oa-ds__edit-run"
            data-testid="edit-run"
            onClick={() => onRunEdit(preview)}
          >
            새 데이터셋으로 편집 실행
          </button>
        </div>
      )}
    </section>
  );
}
