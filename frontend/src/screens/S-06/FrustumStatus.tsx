// Camera-frustum trust status (CG-G-S06g). The 3D frustum itself is drawn by the
// shared viewport (WP-G-02); this panel renders whether that frustum can be
// trusted. A frustum is placed from a camera's hand-eye extrinsic, so a stale
// hand-eye means the frustum is drawn in the wrong place — this panel shows the
// frustum stale for exactly those cameras. Staleness is a backend fact; the
// screen judges nothing.

import type { HandEyeView } from "./handEye";

interface FrustumStatusProps {
  results: readonly HandEyeView[];
  // Whether the depth frustum layer is rendered at all (false under RGB-only).
  depthLayerEnabled: boolean;
}

export function FrustumStatus({ results, depthLayerEnabled }: FrustumStatusProps) {
  return (
    <section className="oa-cam__panel" aria-labelledby="oa-cam-frustum-title">
      <h2 id="oa-cam-frustum-title" className="oa-cam__panel-title">
        프러스텀 연동 상태
      </h2>
      <p className="oa-cam__panel-note">
        프러스텀은 hand-eye 외부 파라미터에서 배치된다. 캘리브가 stale이면 프러스텀은 잘못된 위치에
        그려지므로 stale로 표시한다.
      </p>
      <ul className="oa-cam__frustum-list">
        {results.map((view) => (
          <li
            key={view.slot}
            className="oa-cam__frustum-row"
            data-frustum-slot={view.slot}
            data-frustum-stale={view.stale ? "true" : "false"}
          >
            <span className="oa-cam__frustum-slot">{view.slot}</span>
            <span
              className={`oa-cam__badge ${
                view.stale ? "oa-cam__badge--stale" : "oa-cam__badge--fresh"
              }`}
            >
              {view.stale ? "프러스텀 STALE" : "프러스텀 정상"}
            </span>
            <span className="oa-cam__frustum-when">{view.capturedLabel}</span>
          </li>
        ))}
      </ul>
      {depthLayerEnabled ? null : (
        <p className="oa-cam__frustum-reduced" role="status" data-frustum-depth-removed="true">
          RGB-only 축소 — 프러스텀 뎁스 레이어 제거됨
        </p>
      )}
    </section>
  );
}
