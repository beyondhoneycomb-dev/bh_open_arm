// The collision-event log — a view of the backend event ring buffer (FR-SAF-065),
// newest first. A latched event holds until the operator acknowledges it
// (FR-SAF-043 latch_until_ack); the ack is an intent the backend acts on, and the
// row stays marked latched until the backend reports it cleared.

import type { SafetyEvent } from "./source";
import { reactionSpec } from "./reactionPolicy";

interface EventLogProps {
  events: readonly SafetyEvent[];
  nowMonoMs: number;
  onAcknowledgeEvent: (id: string) => void;
}

function ageSeconds(nowMonoMs: number, tMonoMs: number): string {
  return `${Math.max(0, (nowMonoMs - tMonoMs) / 1000).toFixed(1)}s 전`;
}

export function EventLog({ events, nowMonoMs, onAcknowledgeEvent }: EventLogProps) {
  return (
    <section className="oa-safety__panel" aria-labelledby="oa-safety-events-title">
      <h2 id="oa-safety-events-title" className="oa-safety__panel-title">
        충돌 이벤트 로그
      </h2>

      {events.length === 0 ? (
        <p className="oa-safety__status-line">이벤트 없음</p>
      ) : (
        <ul className="oa-events">
          {events.map((event) => (
            <li
              key={event.id}
              className={`oa-events__row${event.latched ? " oa-events__row--latched" : ""}`}
              data-event={event.id}
              data-latched={event.latched}
            >
              <span className="oa-events__cause">{event.cause}</span>
              <span className="oa-events__meta">{ageSeconds(nowMonoMs, event.tMonoMs)}</span>
              <span className="oa-events__meta">
                반응 {reactionSpec(event.reaction).label} · 관절 {event.joints.join(", ")}
              </span>
              {event.latched && (
                <span className="oa-events__latch">
                  래치 유지 —{" "}
                  <button
                    type="button"
                    className="oa-safety__btn oa-safety__btn--ghost"
                    data-action="ack-event"
                    onClick={() => onAcknowledgeEvent(event.id)}
                  >
                    확인 (ack)
                  </button>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
