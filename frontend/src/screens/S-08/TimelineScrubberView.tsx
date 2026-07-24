// The timeline scrubber (WP-3D-01 viewer). It drives ONE cursor frame index that the
// channel plot and the camera-synced playback both read, so the plot trace and every
// camera tile show the same frame (FR-DAT-014). The axis it scrubs is the synthetic
// grid `timestamp = frame_index / fps`; the note states that this is a grid
// coordinate and NOT capture time (CG-G-S08c) — capture jitter is read from the
// separate capture_ts view, never off this axis.

import type { TimeAxis } from "./types";

export interface TimelineScrubberViewProps {
  timeAxis: TimeAxis;
  cursorFrame: number;
  onScrub: (frameIndex: number) => void;
}

export function TimelineScrubberView({ timeAxis, cursorFrame, onScrub }: TimelineScrubberViewProps) {
  const lastFrame = timeAxis.frameIndices.length - 1;
  const gridSeconds = timeAxis.timestamps[cursorFrame] ?? 0;

  return (
    <section className="oa-ds__scrubber" aria-labelledby="oa-ds-scrubber-title">
      <h2 id="oa-ds-scrubber-title" className="oa-ds__section-title">
        타임라인
      </h2>
      <input
        type="range"
        className="oa-ds__scrubber-range"
        min={0}
        max={Math.max(0, lastFrame)}
        step={1}
        value={cursorFrame}
        aria-label="프레임 스크럽"
        data-testid="scrubber-range"
        onChange={(event) => onScrub(Number(event.target.value))}
      />
      <dl className="oa-ds__scrubber-readout">
        <div className="oa-ds__scrubber-row">
          <dt>frame_index</dt>
          <dd data-testid="scrubber-frame">{cursorFrame}</dd>
        </div>
        <div className="oa-ds__scrubber-row">
          <dt>timestamp (합성 그리드)</dt>
          <dd data-testid="scrubber-grid-seconds">{gridSeconds.toFixed(4)} s</dd>
        </div>
      </dl>
      <p className="oa-ds__scrubber-note" data-testid="scrubber-synthetic-note">
        {timeAxis.domainNote}
      </p>
    </section>
  );
}
