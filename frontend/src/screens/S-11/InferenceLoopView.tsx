// The inference-loop view (11 §2.2). It renders the live rollout loop state — the lifecycle
// phase, the strategy, episode progress, and the effective control rate (fps ×
// interpolation_multiplier). It is read-only status; the start/stop and takeover controls
// live in their own panels. The engine name is stated so an operator sees this is the
// `lerobot-rollout` embed, not the gym-only eval path.

import type { InferenceLoopState } from "./types";
import { ROLLOUT_ENGINE } from "./types";

export interface InferenceLoopViewProps {
  loop: InferenceLoopState;
  policyId: string;
}

export function InferenceLoopView({ loop, policyId }: InferenceLoopViewProps) {
  const episodeText =
    loop.totalEpisodes === null
      ? `${loop.episodeIndex} / ∞ (24/7)`
      : `${loop.episodeIndex} / ${loop.totalEpisodes}`;

  return (
    <section
      className="oa-inf__loop"
      aria-labelledby="oa-inf-loop-title"
      data-testid="inference-loop"
      data-phase={loop.phase}
    >
      <h2 id="oa-inf-loop-title" className="oa-inf__section-title">
        추론 루프
      </h2>
      <dl className="oa-inf__loop-grid">
        <div>
          <dt>엔진</dt>
          <dd data-testid="rollout-engine">{ROLLOUT_ENGINE}</dd>
        </div>
        <div>
          <dt>정책</dt>
          <dd>{policyId}</dd>
        </div>
        <div>
          <dt>단계</dt>
          <dd>
            <span className="oa-inf__phase-pill" data-testid="loop-phase" data-phase={loop.phase}>
              {loop.phase}
            </span>
          </dd>
        </div>
        <div>
          <dt>전략</dt>
          <dd data-testid="loop-strategy">{loop.strategy}</dd>
        </div>
        <div>
          <dt>에피소드</dt>
          <dd data-testid="loop-episode">{episodeText}</dd>
        </div>
        <div>
          <dt>제어 주파수</dt>
          <dd>
            {loop.controlHz} Hz <span className="oa-inf__muted">(fps {loop.fps})</span>
          </dd>
        </div>
      </dl>
    </section>
  );
}
