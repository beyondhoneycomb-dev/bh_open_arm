// The rollout start/stop control. There is ONE start affordance; it is disabled whenever a
// blocker stands (schema lock, a verdict-blocked backend/optimization, a load-preflight
// refusal, a checkpoint<->dataset block, or no active task), and it invokes the screen's
// single `start_rollout` emitter (CG-G-S11e) — LOCAL and ASYNC both flow through it. The
// block reasons are shown so the operator sees why start is unavailable.

export interface RolloutControlViewProps {
  canStart: boolean;
  blockReasons: readonly string[];
  running: boolean;
  onStart: () => void;
  onStop: () => void;
}

export function RolloutControlView({ canStart, blockReasons, running, onStart, onStop }: RolloutControlViewProps) {
  return (
    <section className="oa-inf__rollout" aria-labelledby="oa-inf-rollout-title" data-testid="rollout-control">
      <h2 id="oa-inf-rollout-title" className="oa-inf__section-title">
        롤아웃
      </h2>

      {blockReasons.length > 0 && (
        <ul className="oa-inf__block-reasons" data-testid="rollout-block-reasons">
          {blockReasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}

      <div className="oa-inf__rollout-actions">
        <button
          type="button"
          className="oa-inf__btn oa-inf__btn--primary"
          data-testid="rollout-start"
          disabled={!canStart}
          onClick={onStart}
        >
          롤아웃 시작
        </button>
        <button
          type="button"
          className="oa-inf__btn"
          data-testid="rollout-stop"
          disabled={!running}
          onClick={onStop}
        >
          롤아웃 중지
        </button>
      </div>
    </section>
  );
}
