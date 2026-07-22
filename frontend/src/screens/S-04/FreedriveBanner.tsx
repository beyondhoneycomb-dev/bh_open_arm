// The Freedrive banner (CG-G-S04g). When the backend reports Freedrive active,
// EVERY screen must carry a standing banner: in Freedrive the arm is hand-guided
// and, until the torque path lands, gravity-uncompensated (it sags, FR-MAN-035),
// so an operator on any screen must know the arm is loose.
//
// The banner is a PURE function of backend Freedrive state, invariant to which
// screen is active — it takes an optional currentScreen only to make that
// invariance testable (CG-G-S04g iterates every ScreenId and the banner renders
// identically). Its all-screens reach comes from the backend fact, not from S-04
// being on screen; the always-on global surface (WP-G-03) is where it is hoisted,
// exactly as DummyModeBanner is. Rendered only when active, null otherwise.

import type { ScreenId } from "../../routes/registry";
import type { FreedriveStatus } from "./manualSource";

export interface FreedriveBannerProps {
  status: FreedriveStatus;
  // Present so the invariance is explicit and testable; never gated on.
  currentScreen?: ScreenId;
}

export function FreedriveBanner({ status }: FreedriveBannerProps) {
  if (!status.active) {
    return null;
  }
  const sideLabel = status.side ? `${status.side} 팔` : "팔";
  return (
    <div className="oa-man-freedrive-banner" role="alert" data-freedrive="active">
      <strong>Freedrive 활성 — {sideLabel} 핸드가이드 중</strong>
      {!status.gravityCompensated && <span>중력 미보상 — 팔이 처집니다</span>}
      {!status.frictionCompensated && <span>마찰 미보상</span>}
    </div>
  );
}
