// The preflight banner (FR-GUI-071). Lists the six checks and their pass/fail
// state, and exposes a start control that is disabled whenever the gate is not
// clear (CG-G-03f). The banner offers no "proceed anyway" affordance: when a
// check fails the only listed remedy is to fix the check. The start button calls
// onStart only when canStartSession is true.

import {
  PREFLIGHT_ITEM_IDS,
  PREFLIGHT_ITEM_LABELS,
  canStartSession,
  failedPreflightItems,
  type PreflightItem,
} from "./preflight";

export interface PreflightBannerProps {
  items: readonly PreflightItem[];
  // The session the gate protects (collect or teleop), shown in the button label.
  sessionLabel: string;
  onStart: () => void;
}

export function PreflightBanner({ items, sessionLabel, onStart }: PreflightBannerProps) {
  const byId = new Map(items.map((item) => [item.id, item] as const));
  const canStart = canStartSession(items);
  const failures = failedPreflightItems(items);

  return (
    <section
      className={`oa-preflight ${canStart ? "oa-preflight--ready" : "oa-preflight--blocked"}`}
      aria-label="프리플라이트"
      data-preflight-ready={canStart}
    >
      <ul className="oa-preflight__list">
        {PREFLIGHT_ITEM_IDS.map((id) => {
          const item = byId.get(id);
          const passed = item?.passed ?? false;
          return (
            <li
              key={id}
              className={`oa-preflight__item oa-preflight__item--${passed ? "pass" : "fail"}`}
              data-preflight-item={id}
              data-passed={passed}
            >
              <span className="oa-preflight__mark" aria-hidden="true">
                {passed ? "✓" : "✕"}
              </span>
              <span className="oa-preflight__label">{PREFLIGHT_ITEM_LABELS[id]}</span>
              {!passed && item?.detail && (
                <span className="oa-preflight__detail">{item.detail}</span>
              )}
            </li>
          );
        })}
      </ul>
      {!canStart && (
        <p className="oa-preflight__blocked-note" role="status">
          {failures.length}개 항목 미통과 — 시작 차단됨. 항목을 해결해야 시작할 수 있습니다.
        </p>
      )}
      <button
        type="button"
        className="oa-preflight__start"
        onClick={onStart}
        disabled={!canStart}
      >
        {sessionLabel} 시작
      </button>
    </section>
  );
}
