// The episode-loop FSM view (WP-G-S07): start -> success/fail/cancel -> reset ->
// repeat. It renders the current phase and offers exactly the controls the FSM
// allows from it (episodeFsm.isAllowed); every control emits an episode intent, and
// none is a safety stop (CG-G-S07a). The session-stop control here is
// `session_stop` — it ends the record_loop, distinct from the hard E-Stop that
// lives in the global safety bar.
// The backend `events` dict is mirrored read-only so the operator sees which flag
// the loop is about to act on.

import { EPISODE_EVENTS, isAllowed, type EpisodeEvent, type EpisodePhase } from "./episodeFsm";
import type { EpisodeControlState } from "./types";

export interface EpisodeLoopViewProps {
  phase: EpisodePhase;
  events: EpisodeControlState;
  recordedEpisodeCount: number;
  // Whether the session-start preconditions hold (preflight + disk + push_to_hub).
  // Applies only to the `start` control; the backend is the final authority.
  canStart: boolean;
  onEvent: (event: EpisodeEvent) => void;
}

const PHASE_LABELS: Record<EpisodePhase, string> = {
  idle: "대기 (세션 비활성)",
  recording: "녹화 중",
  reset: "리셋 — 다음 에피소드 준비",
};

const EVENT_LABELS: Record<EpisodeEvent, string> = {
  start: "세션 시작",
  success: "성공",
  fail: "실패",
  cancel: "취소 (재녹화)",
  advance: "다음 에피소드",
  stop: "세션 정지",
};

// A control is offered when the FSM allows the transition; `start` additionally
// requires the start gate to be open.
function controlEnabled(phase: EpisodePhase, event: EpisodeEvent, canStart: boolean): boolean {
  if (!isAllowed(phase, event)) {
    return false;
  }
  return event === "start" ? canStart : true;
}

export function EpisodeLoopView({
  phase,
  events,
  recordedEpisodeCount,
  canStart,
  onEvent,
}: EpisodeLoopViewProps) {
  return (
    <section className="oa-collect__loop" aria-labelledby="oa-collect-loop-title">
      <h2 id="oa-collect-loop-title" className="oa-collect__section-title">
        에피소드 루프
      </h2>

      <p className="oa-collect__phase" role="status" data-testid="episode-phase" data-phase={phase}>
        상태: <strong>{PHASE_LABELS[phase]}</strong>
        <span className="oa-collect__episode-count"> · 기록된 에피소드 {recordedEpisodeCount}</span>
      </p>

      <div className="oa-collect__loop-controls" role="group" aria-label="에피소드 제어">
        {EPISODE_EVENTS.map((event) => (
          <button
            key={event}
            type="button"
            className={`oa-collect__loop-btn oa-collect__loop-btn--${event}`}
            data-event={event}
            disabled={!controlEnabled(phase, event, canStart)}
            onClick={() => onEvent(event)}
          >
            {EVENT_LABELS[event]}
          </button>
        ))}
      </div>

      <dl className="oa-collect__events" data-testid="events-dict" aria-label="record_loop events">
        <div className="oa-collect__event">
          <dt>exit_early</dt>
          <dd>{events.exitEarly ? "true" : "false"}</dd>
        </div>
        <div className="oa-collect__event">
          <dt>rerecord_episode</dt>
          <dd>{events.rerecordEpisode ? "true" : "false"}</dd>
        </div>
        <div className="oa-collect__event">
          <dt>stop_recording</dt>
          <dd>{events.stopRecording ? "true" : "false"}</dd>
        </div>
      </dl>

      <p className="oa-collect__loop-note">
        에피소드 제어는 안전 정지가 아닙니다. 낙하 위험 시에는 전역 안전 바의 하드 정지를 사용하세요.
      </p>
    </section>
  );
}
