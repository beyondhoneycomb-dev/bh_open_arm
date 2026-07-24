// The observation.state channel plot (WP-3D-01 viewer, CG-G-S08a/g). The channel
// selector is the dataset's `names` list, and the selected channel's series is pulled
// by `resolveStateChannel`, which indexes by NAME — so the plot stays correct when
// use_velocity_and_torque toggles the state between 24-dim and 8-dim and every
// column moves (a fixed index would silently scramble the trace). The Y axis carries
// the channel's own unit (.pos=deg / .vel=deg/s / .torque=Nm), because one state
// vector mixes all three and an unlabelled axis misreads a torque as degrees.

import { axisLabel, resolveStateChannel } from "./channels";
import type { EpisodeSignals } from "./types";

export interface ChannelPlotViewProps {
  signals: EpisodeSignals;
  selectedChannel: string;
  cursorFrame: number;
  onSelectChannel: (name: string) => void;
}

const PLOT_WIDTH = 480;
const PLOT_HEIGHT = 140;
const PLOT_PADDING = 8;

// Map a series to an SVG polyline over the plot box. Pure layout math on already-
// resolved values — no domain logic, no channel selection by position.
function polylinePoints(values: readonly number[]): string {
  if (values.length === 0) {
    return "";
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const innerWidth = PLOT_WIDTH - PLOT_PADDING * 2;
  const innerHeight = PLOT_HEIGHT - PLOT_PADDING * 2;
  const step = values.length > 1 ? innerWidth / (values.length - 1) : 0;
  return values
    .map((value, frame) => {
      const x = PLOT_PADDING + frame * step;
      const y = PLOT_PADDING + innerHeight * (1 - (value - min) / span);
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}

export function ChannelPlotView({
  signals,
  selectedChannel,
  cursorFrame,
  onSelectChannel,
}: ChannelPlotViewProps) {
  const series = resolveStateChannel(signals, selectedChannel);
  const points = polylinePoints(series.values);
  const innerWidth = PLOT_WIDTH - PLOT_PADDING * 2;
  const step =
    series.values.length > 1 ? innerWidth / (series.values.length - 1) : 0;
  const cursorX = PLOT_PADDING + Math.min(cursorFrame, series.values.length - 1) * step;
  const cursorValue = series.values[Math.min(cursorFrame, series.values.length - 1)];

  return (
    <section className="oa-ds__plot" aria-labelledby="oa-ds-plot-title">
      <h2 id="oa-ds-plot-title" className="oa-ds__section-title">
        채널 플롯
      </h2>

      <label className="oa-ds__plot-select">
        <span>채널</span>
        <select
          value={selectedChannel}
          data-testid="channel-select"
          onChange={(event) => onSelectChannel(event.target.value)}
        >
          {signals.stateNames.map((name) => (
            <option key={name} value={name}>
              {axisLabel(name)}
            </option>
          ))}
        </select>
      </label>

      <p className="oa-ds__plot-axis" data-testid="plot-axis-label">
        {axisLabel(series.name)}
      </p>

      <svg
        className="oa-ds__plot-svg"
        viewBox={`0 0 ${PLOT_WIDTH} ${PLOT_HEIGHT}`}
        role="img"
        aria-label={`${series.name} 시계열 (${series.unit})`}
        data-testid="channel-plot-svg"
        data-channel={series.name}
        data-unit={series.unit}
      >
        <polyline
          className="oa-ds__plot-line"
          fill="none"
          points={points}
          data-testid="channel-plot-line"
        />
        <line
          className="oa-ds__plot-cursor"
          x1={cursorX}
          x2={cursorX}
          y1={PLOT_PADDING}
          y2={PLOT_HEIGHT - PLOT_PADDING}
          data-testid="plot-cursor"
        />
      </svg>

      <p className="oa-ds__plot-cursor-readout" data-testid="plot-cursor-value">
        frame {cursorFrame}: {cursorValue?.toFixed(3)} {series.unit}
      </p>
    </section>
  );
}
