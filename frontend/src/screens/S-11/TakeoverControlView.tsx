// The takeover control (FR-INF-048). A human can take control of an autonomous rollout and
// hand it back; the trigger and its key/pedal bindings are the backend's config, rendered
// read-only. The screen sends the takeover/release intent — it owns no binding truth and
// disables the controls on a schema lock.

import type { TakeoverControl } from "./types";

export interface TakeoverControlViewProps {
  takeover: TakeoverControl;
  disabled: boolean;
  onTakeover: () => void;
  onRelease: () => void;
}

export function TakeoverControlView({ takeover, disabled, onTakeover, onRelease }: TakeoverControlViewProps) {
  const human = takeover.humanInControl;
  return (
    <section
      className="oa-inf__takeover"
      aria-labelledby="oa-inf-takeover-title"
      data-testid="takeover-control"
      data-human-in-control={human}
    >
      <h2 id="oa-inf-takeover-title" className="oa-inf__section-title">
        제어권 개입 (takeover)
      </h2>

      <p className="oa-inf__takeover-state" data-testid="takeover-state">
        현재 제어: {human ? "사람 (개입 중)" : "정책 (자율)"}
      </p>

      <div className="oa-inf__takeover-actions">
        <button
          type="button"
          className="oa-inf__btn oa-inf__btn--warn"
          data-testid="takeover-btn"
          disabled={disabled || human}
          onClick={onTakeover}
        >
          제어권 개입
        </button>
        <button
          type="button"
          className="oa-inf__btn"
          data-testid="release-btn"
          disabled={disabled || !human}
          onClick={onRelease}
        >
          제어권 반환
        </button>
      </div>

      <dl className="oa-inf__bindings">
        <div>
          <dt>트리거</dt>
          <dd>{takeover.trigger}</dd>
        </div>
        <div>
          <dt>pause/resume</dt>
          <dd>
            <kbd>{takeover.pauseResumeBinding}</kbd>
          </dd>
        </div>
        <div>
          <dt>correction</dt>
          <dd>
            <kbd>{takeover.correctionBinding}</kbd>
          </dd>
        </div>
        <div>
          <dt>upload</dt>
          <dd>
            <kbd>{takeover.uploadBinding}</kbd>
          </dd>
        </div>
      </dl>
    </section>
  );
}
