// The recent-sessions list and the unacked-warning tally (FR-GUI-100). Both are
// backend-supplied: the session summaries are listed as given (ranked nowhere),
// and the unacked count and its highest severity come from the notification
// center (WP-G-03). The dashboard mirrors the tally and decides no severity.

import { RENDER_STATE_CLASS, RENDER_STATE_LABEL } from "./severity";
import type { RecentSession, UnackedWarnings } from "./types";
import { UNAVAILABLE } from "./types";

interface SessionsViewProps {
  sessions: readonly RecentSession[];
  unacked: UnackedWarnings;
}

export function SessionsView({ sessions, unacked }: SessionsViewProps) {
  const severity = unacked.highestSeverity ?? UNAVAILABLE;
  return (
    <section className="oa-dash__panel" aria-labelledby="oa-dash-sessions-title">
      <h2 id="oa-dash-sessions-title" className="oa-dash__panel-title">
        최근 세션 · 미ack 경고
      </h2>

      <div
        className={`oa-dash__tile ${unacked.highestSeverity === null ? "" : RENDER_STATE_CLASS[severity]}`}
        data-testid="fr100-unacked"
        data-unacked-count={unacked.count}
      >
        <span className="oa-dash__tile-label">미ack 경고 수</span>
        <span className="oa-dash__tile-value" data-testid="unacked-count">
          {unacked.count}
        </span>
        <span className="oa-dash__tile-sub" data-testid="unacked-severity">
          최고 심각도: {unacked.highestSeverity === null ? "없음" : RENDER_STATE_LABEL[severity]}
        </span>
      </div>

      <ul className="oa-dash__sessions" data-testid="fr100-sessions" data-session-count={sessions.length}>
        {sessions.length === 0 ? (
          <li className="oa-dash__session-empty" data-testid="sessions-empty">
            최근 세션 없음
          </li>
        ) : (
          sessions.map((session) => (
            <li key={session.id} className="oa-dash__session" data-testid={`session-${session.id}`}>
              <span className="oa-dash__session-name">{session.name}</span>
              <span className="oa-dash__session-meta">
                {session.startedDisplay} · {session.episodeCount} 에피소드 · {session.outcome}
              </span>
            </li>
          ))
        )}
      </ul>
    </section>
  );
}
