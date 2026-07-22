// The VR link watchdog (FR-TEL-081/094). It renders the backend `LinkHeartbeat`
// verdict — LIVE or LOST — plus the readings the operator needs to see the link's
// health: measured receive Hz, jitter, last-frame age, tracking validity. STALE is
// a LOST link because `treatStaleAsLost` is frozen true (STALE is indistinguishable
// downstream from a normal stop). Every value is a backend reading; the screen
// decides no timeout and judges no age itself — that safety timeout is server-clock,
// backend-owned.

import type { WatchdogStatus } from "./teleopSource";

function ms(value: number | null): string {
  return value === null ? "—" : `${value.toFixed(1)} ms`;
}

function hz(value: number | null): string {
  return value === null ? "—" : `${value.toFixed(1)} Hz`;
}

interface HeartbeatWatchdogProps {
  watchdog: WatchdogStatus;
}

export function HeartbeatWatchdog({ watchdog }: HeartbeatWatchdogProps) {
  return (
    <section className="oa-tel__watchdog" aria-label="링크 워치독">
      <h2 className="oa-tel__h2">링크 워치독 (하트비트)</h2>

      <p
        className="oa-tel__link-health"
        role="status"
        data-field="link-health"
        data-health={watchdog.linkHealth}
      >
        링크: {watchdog.linkHealth === "live" ? "LIVE" : "LOST"} · tracking {watchdog.trackingValidity}
      </p>

      <dl className="oa-tel__kv">
        <div>
          <dt>수신 레이트</dt>
          <dd data-field="measured-hz">{hz(watchdog.measuredHz)}</dd>
        </div>
        <div>
          <dt>지터</dt>
          <dd data-field="jitter">{ms(watchdog.jitterMs)}</dd>
        </div>
        <div>
          <dt>마지막 프레임 경과</dt>
          <dd data-field="last-frame-age">{ms(watchdog.lastFrameAgeMs)}</dd>
        </div>
        <div>
          <dt>하트비트 타임아웃</dt>
          <dd data-field="hb-timeout">
            {watchdog.heartbeatTimeoutMs} ms ({watchdog.heartbeatTimeoutMin}–{watchdog.heartbeatTimeoutMax})
          </dd>
        </div>
      </dl>

      <p className="oa-tel__hint">
        treat_stale_as_lost = {watchdog.treatStaleAsLost ? "true (동결)" : "false"} — STALE는 링크 소실로 취급.
        타임아웃 초과 = LINK_LOST(S5), 감속 후 홀드 (명령 스트림 중단 없음).
      </p>
    </section>
  );
}
