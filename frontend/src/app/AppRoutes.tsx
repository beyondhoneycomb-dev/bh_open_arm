// Route tree built from the canonical registry. This is the only place routes
// are declared, and it declares exactly the registry's set: the 13 screens of
// 13 §2.6 (S-02 contributing two paths) plus /viewport, all under the shared
// Layout. A catch-all renders NotFound. The shell adds no screen the registry
// does not list (CG-G-00b). Router-agnostic (just <Routes>) so tests can wrap it
// in a MemoryRouter and the app wraps it in a BrowserRouter.

import { Route, Routes } from "react-router-dom";

import { SCREENS, VIEWPORT_PATH } from "../routes/registry";
import { Layout } from "./Layout";
import { NotFound } from "./NotFound";
import { ScreenMount } from "./ScreenMount";
import { ViewportRoute } from "./ViewportRoute";

const ROOT_PATH = "/";

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<Layout />}>
        {SCREENS.flatMap((screen) =>
          screen.paths.map((path) =>
            path === ROOT_PATH ? (
              <Route key={path} index element={<ScreenMount screen={screen} />} />
            ) : (
              <Route key={path} path={path} element={<ScreenMount screen={screen} />} />
            ),
          ),
        )}
        <Route path={VIEWPORT_PATH} element={<ViewportRoute />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
