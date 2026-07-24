// Camera-synced playback (WP-3D-01 viewer). Every camera stream is shown at the SAME
// cursor frame the timeline scrubber and the channel plot use, so a frame is read
// across all modalities at once. The stream set is enumerated from info.json image
// features (the backend `CameraStream` list), never a fixed slot table. This WP is
// AI-offline, so a tile stands in for the decoded frame with the synced frame index
// and its dataset image key; a live wave binds the decoded WS camera frame here.

import type { CameraStream } from "./types";

export interface CameraSyncViewProps {
  streams: readonly CameraStream[];
  cursorFrame: number;
}

export function CameraSyncView({ streams, cursorFrame }: CameraSyncViewProps) {
  return (
    <section className="oa-ds__camsync" aria-labelledby="oa-ds-camsync-title">
      <h2 id="oa-ds-camsync-title" className="oa-ds__section-title">
        카메라 동기 재생
      </h2>
      <div className="oa-ds__camsync-grid">
        {streams.map((stream) => (
          <article
            key={stream.imageKey}
            className="oa-ds__camsync-tile"
            data-testid={`camsync-${stream.imageKey}`}
            data-frame={cursorFrame}
          >
            <div className="oa-ds__camsync-frame" aria-hidden="true">
              <span className="oa-ds__camsync-kind">{stream.isDepth ? "DEPTH" : "RGB"}</span>
              <span className="oa-ds__camsync-frameno">frame {cursorFrame}</span>
            </div>
            <p className="oa-ds__camsync-slot">{stream.slot}</p>
            <p className="oa-ds__camsync-key">{stream.imageKey}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
