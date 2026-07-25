// The nine §4.3 subsystem rows (CG-5-02a), severity-sorted. Each row renders its
// diagnostic state — OK / WARN / ERROR / STALE — or UNAVAILABLE when its source
// has not landed (never OK, CG-G-S01e). The row shows the backend's state and
// detail verbatim; it decides nothing.

import { RENDER_STATE_CLASS, RENDER_STATE_LABEL, bySeverity, subsystemRenderState } from "./severity";
import type { SubsystemStatus } from "./types";

interface SubsystemGridViewProps {
  subsystems: readonly SubsystemStatus[];
}

export function SubsystemGridView({ subsystems }: SubsystemGridViewProps) {
  const ordered = bySeverity(subsystems);
  return (
    <section className="oa-dash__panel" data-testid="subsystem-grid" aria-labelledby="oa-dash-subsys-title">
      <h2 id="oa-dash-subsys-title" className="oa-dash__panel-title">
        서브시스템 상태 (14 §4.3)
      </h2>
      <ul className="oa-dash__subsys-list">
        {ordered.map((subsystem) => {
          const renderState = subsystemRenderState(subsystem);
          return (
            <li
              key={subsystem.id}
              className={`oa-dash__subsys ${RENDER_STATE_CLASS[renderState]}`}
              data-testid={`subsystem-${subsystem.id}`}
              data-render-state={renderState}
              data-critical={subsystem.critical}
            >
              <span className="oa-dash__subsys-label">{subsystem.label}</span>
              <span className="oa-dash__subsys-state" data-testid={`subsystem-state-${subsystem.id}`}>
                {RENDER_STATE_LABEL[renderState]}
              </span>
              <span className="oa-dash__subsys-detail">{subsystem.detail}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
