// The camera FPS/jitter tiles (FR-GUI-100). The tile count is the LENGTH of the
// active-stream array — never a hardcoded constant (CG-G-S01c / CG-5-02b): add or
// drop a stream and the tile set follows. Each tile shows the UI label and the
// dataset key (they differ, per-arm prefix) and the fps/jitter numbers verbatim;
// the per-stream state is the backend's, thresholded nowhere here. An empty array
// renders an explicit "no active stream" tile, never an empty region reading OK.

import { RENDER_STATE_CLASS, RENDER_STATE_LABEL } from "./severity";
import type { CameraStreamStat } from "./types";
import { UNAVAILABLE } from "./types";

interface CameraStatusViewProps {
  cameras: readonly CameraStreamStat[];
}

export function CameraStatusView({ cameras }: CameraStatusViewProps) {
  const empty = cameras.length === 0;
  return (
    <section className="oa-dash__panel" aria-labelledby="oa-dash-cam-title">
      <h2 id="oa-dash-cam-title" className="oa-dash__panel-title">
        카메라 FPS / 지터
      </h2>
      <div className="oa-dash__cam-grid" data-testid="fr100-cameras" data-stream-count={cameras.length}>
        {empty ? (
          <p className="oa-dash__cam-empty" data-testid="cameras-empty" role="status">
            활성 전송 스트림 없음
          </p>
        ) : (
          cameras.map((camera) => {
            const renderState = camera.state ?? UNAVAILABLE;
            return (
              <div
                key={camera.slot}
                className={`oa-dash__cam-tile ${RENDER_STATE_CLASS[renderState]}`}
                data-testid={`camera-tile-${camera.slot}`}
                data-render-state={renderState}
              >
                <span className="oa-dash__cam-uilabel">{camera.uiLabel}</span>
                <span className="oa-dash__cam-key">{camera.datasetKey}</span>
                <span className="oa-dash__cam-fps" data-testid={`camera-fps-${camera.slot}`}>
                  {camera.fps} fps · 지터 {camera.jitterMs} ms
                </span>
                <span className="oa-dash__cam-state">{RENDER_STATE_LABEL[renderState]}</span>
              </div>
            );
          })
        )}
      </div>
    </section>
  );
}
