// The persistent shell chrome: a nav rail linking every screen plus the viewport
// route, and an outlet the active route renders into. Nav entries come straight
// from the canonical registry, so the shell can never drift from 13 §2.6. Layout
// density and sidebar state read from the shared runtime config.
//
// The safety surface sits above the outlet rather than inside any screen, which is what
// makes it unconditional: it is a sibling of the outlet, so no route, redirect, or screen
// error can replace it, and every route inherits it (CG-G-03b, FR-GUI-065). The screen
// error half of that is enforced by ScreenErrorBoundary, not by the sibling position —
// a throw unwinds past siblings, and the boundary is what stops it below this surface.

import { NavLink, Outlet, useLocation } from "react-router-dom";

import { SCREENS, VIEWPORT_PATH } from "../routes/registry";
import { useConfig } from "./ConfigContext";
import { ControlLeaseHost } from "./ControlLeaseHost";
import { ModeAuthorityTable } from "../mode/ModeAuthorityTable";
import { ScreenErrorBoundary } from "./ScreenErrorBoundary";
import { SafetyBarHost } from "./SafetyBarHost";

export function Layout() {
  const { config, status } = useConfig();
  const { pathname } = useLocation();
  const collapsed = config.layout.sidebarCollapsed;

  return (
    <div className={`oa-shell oa-shell--${config.layout.density}`}>
      <nav className={`oa-nav${collapsed ? " oa-nav--collapsed" : ""}`} aria-label="주 메뉴">
        <p className="oa-nav__brand">OpenArm</p>
        <ul className="oa-nav__list">
          {SCREENS.map((screen) => (
            <li key={screen.id}>
              <NavLink to={screen.paths[0]} end className="oa-nav__link">
                {screen.title}
              </NavLink>
            </li>
          ))}
          <li>
            <NavLink to={VIEWPORT_PATH} className="oa-nav__link">
              3D 뷰포트
            </NavLink>
          </li>
        </ul>
        <p className="oa-nav__status" data-status={status}>
          config: {status}
        </p>
      </nav>
      <main className="oa-main">
        <SafetyBarHost />
        <ControlLeaseHost />
        {/* Reference, not state: which mode may command, and the one mode (MOTOR_SETUP) in
            which an external CAN client is allowed because the backend does not hold the bus
            (FR-GUI-080/086). Collapsed by default — it belongs beside the lease, and it is not
            worth the vertical space of every screen. No mode is passed because nothing in this
            build reports one, and a marked row reads as a rig that is in that mode.

            Like its two neighbours this renders above the error boundary, where a throw
            would take the document down. It maps a frozen constant array and receives
            nothing from outside, so it has no branch that can throw; the alternative —
            moving it below the boundary — would hide the authority reference exactly when
            a screen has failed and the operator is working out what may still command. */}
        <details className="oa-authority">
          <summary className="oa-authority__summary">모드별 제어권</summary>
          <ModeAuthorityTable activeMode={null} />
        </details>
        <div className="oa-main__content">
          {/* Keyed by path so a failed screen does not blank the next one the operator
              picks from the nav rail — see ScreenErrorBoundary.

              SafetyBarHost is deliberately OUTSIDE the boundary. Wrapping it too would
              trade a blank page for a page that looks healthy and has no stop control,
              and an operator reads the second one as a working rig. A throw there should
              take the document down, because that is unmistakable. */}
          <ScreenErrorBoundary key={pathname}>
            <Outlet />
          </ScreenErrorBoundary>
        </div>
      </main>
    </div>
  );
}
