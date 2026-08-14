// Standalone /viewport route (FR-GUI-003). The shell owns that this route exists;
// what it shows is WP-G-02's shared viewport, imported through that subtree's public
// surface rather than rebuilt here — the same component the five embedding screens
// render, so the standalone route and an embed cannot drift into two viewports.
//
// The import is lazy for the same reason the screens are (screenResolver.ts): the
// viewport pulls in Three.js and urdf-loader, which is the largest chunk this bundle
// has. A static import from the shell puts all of it in the entry chunk, so every
// screen pays for a 3D renderer it may never show. Suspense covers the load.
//
// No source prop: the panel's own offline default stands in for a backend that is not
// connected, and that default reads stale rather than nominal. Passing a source from
// here would be the shell authoring viewport state it has no backend for.

import { Suspense, lazy } from "react";

const ViewportPanel = lazy(async () => {
  const module = await import("../viewport");
  return { default: module.ViewportPanel };
});

export function ViewportRoute() {
  return (
    <Suspense fallback={<ViewportLoading />}>
      <ViewportPanel />
    </Suspense>
  );
}

// The heading matches the loaded panel's so the route identifies itself the same way
// before and after the chunk arrives, rather than appearing to change screens.
function ViewportLoading() {
  return (
    <section className="oa-scaffold" aria-labelledby="oa-viewport-title">
      <header className="oa-scaffold__head">
        <p className="oa-scaffold__id">/viewport</p>
        <h1 id="oa-viewport-title" className="oa-scaffold__title">
          3D 뷰포트
        </h1>
      </header>
      <p className="oa-scaffold__pending" role="status">
        뷰포트를 불러오는 중입니다.
      </p>
    </section>
  );
}
