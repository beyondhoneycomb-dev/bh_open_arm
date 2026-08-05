// The persistent shell chrome: a nav rail linking every screen plus the viewport
// route, and an outlet the active route renders into. Nav entries come straight
// from the canonical registry, so the shell can never drift from 13 §2.6. Layout
// density and sidebar state read from the shared runtime config.
//
// The safety surface sits above the outlet rather than inside any screen, which is what
// makes it unconditional: it is a sibling of the outlet, so no route, redirect, or screen
// error can replace it, and every route inherits it (CG-G-03b, FR-GUI-065).

import { NavLink, Outlet } from "react-router-dom";

import { SCREENS, VIEWPORT_PATH } from "../routes/registry";
import { useConfig } from "./ConfigContext";
import { SafetyBarHost } from "./SafetyBarHost";

export function Layout() {
  const { config, status } = useConfig();
  const collapsed = config.layout.sidebarCollapsed;

  return (
    <div className={`oa-shell oa-shell--${config.layout.density}`} data-theme={config.theme.mode}>
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
        <div className="oa-main__content">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
