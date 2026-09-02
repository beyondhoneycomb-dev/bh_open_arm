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
// The joint frame is live; the model is not. The telemetry frame carries every joint in
// radians under the name the model is written against, so the snapshot gate and the stream-age
// rule both run on real data — a frame missing a joint the model declares is refused, and the
// stale badge with its control block now reflects a stream that actually stopped.
//
// What is still the offline default is the ASSET: `openarm_description` is not in this
// repository and not on this machine, so nothing serves the URDF, its provenance, or the link
// set. With no model loaded the canvas draws its scene and no robot, which is what a viewport
// with a live pose and no geometry honestly looks like.

import { Suspense, lazy } from "react";

import { useLiveViewportSource } from "./liveViewportSource";

const ViewportPanel = lazy(async () => {
  const module = await import("../viewport");
  return { default: module.ViewportPanel };
});

export function ViewportRoute() {
  const source = useLiveViewportSource();
  return (
    <Suspense fallback={<ViewportLoading />}>
      <ViewportPanel source={source} />
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
