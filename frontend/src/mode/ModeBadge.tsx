// The current-mode badge and transition indicator (FR-GUI-080/082). Shows which
// mode is active and who holds send_action in it, and — while a hand-off is in
// flight — that the transition is the movement of authority under a held stream,
// not a reconnect. It renders backend-owned mode state only; it never triggers a
// transition or touches the link.

import { HOLDER_LABELS, modeById, type ModeId } from "./modes";

export interface ModeBadgeProps {
  mode: ModeId;
  // True while a control hand-off is in flight; the badge then shows the held
  // stream so the operator sees the transition never breaks the CAN stream.
  transitioning: boolean;
}

export function ModeBadge({ mode, transitioning }: ModeBadgeProps) {
  const descriptor = modeById(mode);
  return (
    <div className="oa-mode-badge" role="status" aria-label="현재 모드">
      <span className="oa-mode-badge__id" data-mode={descriptor.id}>
        {descriptor.label}
      </span>
      <span className="oa-mode-badge__holder">
        send_action 권리: {HOLDER_LABELS[descriptor.holder]}
      </span>
      {transitioning ? (
        <span className="oa-mode-badge__transition" role="alert">
          권리 이양 중 — 스트림 유지 (STOP_HOLD)
        </span>
      ) : null}
    </div>
  );
}
