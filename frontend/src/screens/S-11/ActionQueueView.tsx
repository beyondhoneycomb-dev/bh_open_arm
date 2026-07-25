// The action-queue visualization (CG-G-S11f). It renders the async chunk-queue depth from
// the live telemetry the screen subscribes to, re-rendering on every frame — the size is
// bound to the incoming stream, not baked at load. `aria-live` announces the changing depth
// for assistive tech. SYNC / REMOTE_GRPC carry residual 0 (no async queue), which the view
// states rather than hiding.

import type { ActionQueueTelemetry } from "./types";

export interface ActionQueueViewProps {
  telemetry: ActionQueueTelemetry;
}

export function ActionQueueView({ telemetry }: ActionQueueViewProps) {
  const hasQueue = telemetry.backend === "rtc";
  const fillPct =
    telemetry.queueThreshold > 0
      ? Math.min(100, Math.round((telemetry.residualActions / telemetry.queueThreshold) * 100))
      : 0;
  const starved = telemetry.residualActions === 0 && hasQueue;

  return (
    <section
      className="oa-inf__queue"
      aria-labelledby="oa-inf-queue-title"
      data-testid="action-queue"
      data-residual={telemetry.residualActions}
      data-backend={telemetry.backend}
    >
      <h2 id="oa-inf-queue-title" className="oa-inf__section-title">
        액션 큐
      </h2>

      {hasQueue ? (
        <>
          <p className="oa-inf__queue-size" aria-live="polite" data-testid="action-queue-size">
            큐 잔량 <strong data-testid="action-queue-residual">{telemetry.residualActions}</strong>
            {" / "}
            리필 임계 {telemetry.queueThreshold}
          </p>
          <div
            className="oa-inf__queue-bar"
            role="meter"
            aria-valuenow={telemetry.residualActions}
            aria-valuemin={0}
            aria-valuemax={telemetry.queueThreshold}
            data-starved={starved}
          >
            <span className="oa-inf__queue-fill" style={{ width: `${fillPct}%` }} />
          </div>
          <p className="oa-inf__queue-meta">
            보간기 잔량 {telemetry.interpolatorResidual} · 고갈 횟수{" "}
            <span data-testid="action-queue-exhaustion">{telemetry.exhaustionCount}</span> · tick{" "}
            {telemetry.tick}
          </p>
          {starved && (
            <p className="oa-inf__queue-starved" role="status">
              큐 고갈 — 이 틱은 발행 없음 (스케줄러 홀드)
            </p>
          )}
        </>
      ) : (
        <p className="oa-inf__queue-none" data-testid="action-queue-none">
          {telemetry.backend} 백엔드에는 비동기 큐가 없습니다 (잔량 0)
        </p>
      )}
    </section>
  );
}
