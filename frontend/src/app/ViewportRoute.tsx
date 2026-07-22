// Standalone /viewport route (FR-GUI-003). The shared 3D viewport component is
// WP-G-02's deliverable (Three.js + urdf-loader, ROS Z-up -> Y-up); the shell
// only owns that this route exists. WP-G-02 fills it from its own subtree; until
// then this placeholder holds the route so the route count stays 13 + /viewport.

export function ViewportRoute() {
  return (
    <section className="oa-scaffold" aria-labelledby="oa-viewport-title">
      <header className="oa-scaffold__head">
        <p className="oa-scaffold__id">/viewport</p>
        <h1 id="oa-viewport-title" className="oa-scaffold__title">
          3D 뷰포트
        </h1>
      </header>
      <p className="oa-scaffold__pending" role="status">
        공유 3D 뷰포트 미구현 — WP-G-02 착지 대기 (not yet implemented)
      </p>
    </section>
  );
}
