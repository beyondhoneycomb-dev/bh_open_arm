// The Resume panel (CG-G-S07e). An interrupted session (crash / disk-low, detected
// by the backend WP-3C-07) is offered for Resume keyed by its STAMPED repo_id, and
// resuming restores THAT id unchanged — the screen passes `stampedRepoId` straight
// through to the resume intent. It never re-stamps: a second stamp would fork the
// name and the operator would look for a dataset that does not exist. Sessions that
// require a human judgment (crash recovery) are marked so, but resuming is not
// blocked on the not-yet-landed hardware gate.

import type { ResumableSession } from "./types";

export interface ResumeViewProps {
  sessions: readonly ResumableSession[];
  onResume: (stampedRepoId: string) => void;
}

export function ResumeView({ sessions, onResume }: ResumeViewProps) {
  return (
    <section className="oa-collect__resume" aria-labelledby="oa-collect-resume-title">
      <h2 id="oa-collect-resume-title" className="oa-collect__section-title">
        중단 세션 재개
      </h2>
      {sessions.length === 0 ? (
        <p className="oa-collect__resume-empty" data-testid="resume-empty">
          재개할 중단 세션이 없습니다.
        </p>
      ) : (
        <ul className="oa-collect__resume-list">
          {sessions.map((session) => (
            <li
              key={session.stampedRepoId}
              className="oa-collect__resume-row"
              data-testid="resume-row"
            >
              <div className="oa-collect__resume-meta">
                <code className="oa-collect__resume-id" data-testid="resume-id">
                  {session.stampedRepoId}
                </code>
                <span className="oa-collect__resume-detail">
                  에피소드 {session.recordedEpisodes} · {session.reason}
                </span>
                {session.requiresUserJudgment && (
                  <span className="oa-collect__resume-judgment" role="status">
                    사람 판단 필요
                  </span>
                )}
              </div>
              <button
                type="button"
                className="oa-collect__resume-btn"
                onClick={() => onResume(session.stampedRepoId)}
              >
                재개
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
