// The CRITICAL-only area (02c §4.2 mitigation): the highest-severity subsystems
// get a dedicated region so a CRITICAL banner is never lost next to camera FPS.
// Membership is the backend's `critical` flag (e.g. GUI-backend STALE = process
// death = fall risk, 14 §4.3 / F17 OA-SYS-004); the dashboard decides none of it.
// The region is always present — when empty it says so, so its absence is never
// ambiguous.

import { RENDER_STATE_CLASS, RENDER_STATE_LABEL, criticalSubsystems, subsystemRenderState } from "./severity";
import type { SubsystemStatus } from "./types";

interface CriticalAlertsViewProps {
  subsystems: readonly SubsystemStatus[];
}

export function CriticalAlertsView({ subsystems }: CriticalAlertsViewProps) {
  const critical = criticalSubsystems(subsystems);
  const empty = critical.length === 0;
  return (
    <section
      className="oa-dash__critical"
      data-testid="critical-area"
      data-critical-count={critical.length}
      role="region"
      aria-labelledby="oa-dash-critical-title"
    >
      <h2 id="oa-dash-critical-title" className="oa-dash__critical-title">
        CRITICAL
      </h2>
      {empty ? (
        <p className="oa-dash__critical-empty" data-testid="critical-empty" role="status">
          현재 CRITICAL 경보 없음
        </p>
      ) : (
        <ul className="oa-dash__critical-list">
          {critical.map((subsystem) => {
            const renderState = subsystemRenderState(subsystem);
            return (
              <li
                key={subsystem.id}
                className={`oa-dash__critical-item ${RENDER_STATE_CLASS[renderState]}`}
                data-testid={`critical-${subsystem.id}`}
                data-render-state={renderState}
              >
                <span className="oa-dash__critical-label">{subsystem.label}</span>
                <span className="oa-dash__critical-state">{RENDER_STATE_LABEL[renderState]}</span>
                <span className="oa-dash__critical-detail">{subsystem.detail}</span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
