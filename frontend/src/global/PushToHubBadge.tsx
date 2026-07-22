// Always-on badge for push_to_hub (FR-GUI-073). When on, it renders in a danger
// tone with the upload warning and shows private/tags. The badge itself does not
// start a collection; the confirmation gate (pushToHubRequiresConfirm) is applied
// by the collect flow (CG-G-03d), and PushToHubConfirm renders that gate.

import {
  PUSH_TO_HUB_UPLOAD_WARNING,
  pushToHubRequiresConfirm,
  type PushToHubState,
} from "./flags";

export interface PushToHubBadgeProps {
  state: PushToHubState;
}

export function PushToHubBadge({ state }: PushToHubBadgeProps) {
  const danger = state.enabled;
  return (
    <span
      className={`oa-badge ${danger ? "oa-badge--danger" : "oa-badge--nominal"}`}
      data-flag="push_to_hub"
      role="status"
    >
      <span className="oa-badge__key">push_to_hub</span>
      <span className="oa-badge__value">{state.enabled ? "ON" : "OFF"}</span>
      {danger && (
        <>
          <span className="oa-badge__warning">{PUSH_TO_HUB_UPLOAD_WARNING}</span>
          <span className="oa-badge__meta">
            {state.private ? "private" : "public"}
            {state.tags.length > 0 ? ` · ${state.tags.join(", ")}` : ""}
          </span>
        </>
      )}
    </span>
  );
}

export interface PushToHubConfirmProps {
  state: PushToHubState;
  onConfirm: () => void;
  onCancel: () => void;
}

// The explicit confirmation a collection start must pass while push_to_hub is on
// (CG-G-03d). It renders only when the gate applies, and offers no path that
// proceeds without an affirmative click.
export function PushToHubConfirm({ state, onConfirm, onCancel }: PushToHubConfirmProps) {
  if (!pushToHubRequiresConfirm(state)) {
    return null;
  }
  return (
    <div className="oa-confirm" role="alertdialog" aria-label="push_to_hub 확인">
      <p className="oa-confirm__body">{PUSH_TO_HUB_UPLOAD_WARNING}. 계속하시겠습니까?</p>
      <div className="oa-confirm__actions">
        <button type="button" className="oa-confirm__cancel" onClick={onCancel}>
          취소
        </button>
        <button type="button" className="oa-confirm__accept oa-confirm__accept--danger" onClick={onConfirm}>
          업로드를 이해했고 계속
        </button>
      </div>
    </div>
  );
}
