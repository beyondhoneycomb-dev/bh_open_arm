// Freedrive deadman button (WP-G-S04, FR-MAN-029). Freedrive is hold-to-activate
// ONLY: press enters, release exits to a Cat 2 position hold — never a toggle, so
// letting go always stops hand-guiding. The compensation state is the backend's
// (FR-MAN-035): if gravity is uncompensated the arm sags, and the button states
// that standing fact. The button is disabled without control authority; the screen
// also guards the enter/exit emitters, so a release always reaches the hold path.

import type { FreedriveStatus } from "./manualSource";

export interface FreedriveDeadmanProps {
  status: FreedriveStatus;
  enabled: boolean;
  onEnter: () => void;
  onExit: () => void;
}

export function FreedriveDeadman({ status, enabled, onEnter, onExit }: FreedriveDeadmanProps) {
  return (
    <section className="oa-man-freedrive" aria-labelledby="oa-man-freedrive-title">
      <h2 id="oa-man-freedrive-title">Freedrive (중력보상 핸드가이드)</h2>
      <button
        type="button"
        className="oa-man-freedrive__deadman"
        data-field="freedrive-deadman"
        disabled={!enabled}
        aria-pressed={status.active}
        onPointerDown={() => onEnter()}
        onPointerUp={() => onExit()}
        onPointerLeave={() => onExit()}
      >
        누르고 있는 동안 Freedrive
      </button>
      <ul className="oa-man-freedrive__status">
        <li data-field="freedrive-path">경로: {status.path}</li>
        {!status.gravityCompensated && (
          <li className="oa-man-freedrive__warn" role="alert">
            중력 미보상 — 팔이 처집니다
          </li>
        )}
        {!status.frictionCompensated && (
          <li className="oa-man-freedrive__warn" role="note">
            마찰 미보상
          </li>
        )}
      </ul>
    </section>
  );
}
