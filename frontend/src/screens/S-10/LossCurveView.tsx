// The LOCAL loss curve + throughput + log stream (FR-GUI-124, CG-G-S10b/c). Two rules
// are structural here:
//   - the chart plots ONLY the seven MetricsTracker keys (metrics.ts): the metric
//     selector is built from `METRIC_KEYS`, and `isMetricKey` guards the series, so a
//     fabricated key cannot be charted (CG-G-S10b);
//   - the curve renders from the local samples with NO dependency on W&B — this
//     component imports nothing from wandb and reads no remote source, so on an
//     air-gapped host with W&B disabled the loss curve still draws (CG-G-S10c). The
//     `wandbEnabled` flag is shown for honesty; the curve does not require it.

import { useState } from "react";

import { METRIC_KEYS, isMetricKey, metricMeta, type MetricKey } from "./metrics";
import type { MetricSample, MetricsStream } from "./types";

export interface LossCurveViewProps {
  metrics: MetricsStream;
}

const PLOT_WIDTH = 480;
const PLOT_HEIGHT = 160;
const PLOT_PADDING = 10;

interface PlottedPoint {
  step: number;
  value: number;
}

// The (step, value) pairs for one metric key, dropping samples that do not carry it.
function seriesFor(samples: readonly MetricSample[], key: MetricKey): PlottedPoint[] {
  const points: PlottedPoint[] = [];
  for (const sample of samples) {
    const value = sample.values[key];
    if (value !== undefined) {
      points.push({ step: sample.step, value });
    }
  }
  return points;
}

function polylinePoints(points: readonly PlottedPoint[]): string {
  if (points.length === 0) {
    return "";
  }
  const values = points.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const innerWidth = PLOT_WIDTH - PLOT_PADDING * 2;
  const innerHeight = PLOT_HEIGHT - PLOT_PADDING * 2;
  const step = points.length > 1 ? innerWidth / (points.length - 1) : 0;
  return points
    .map((point, index) => {
      const x = PLOT_PADDING + index * step;
      const y = PLOT_PADDING + innerHeight * (1 - (point.value - min) / span);
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}

export function LossCurveView({ metrics }: LossCurveViewProps) {
  const [selectedKey, setSelectedKey] = useState<MetricKey>("loss");
  // The guard is the CG-G-S10b enforcement point: a key that is not a MetricsTracker
  // output can never reach the plot, even if the selector were fed a foreign value.
  const key: MetricKey = isMetricKey(selectedKey) ? selectedKey : "loss";
  const meta = metricMeta(key);
  const points = seriesFor(metrics.samples, key);
  const line = polylinePoints(points);
  const latest = points.length > 0 ? points[points.length - 1] : null;

  return (
    <section className="oa-trn__panel" aria-labelledby="oa-trn-metrics-title" data-testid="loss-curve">
      <h2 id="oa-trn-metrics-title" className="oa-trn__section-title">
        학습 지표 (로컬)
      </h2>

      <p
        className="oa-trn__badge oa-trn__badge--airgap"
        data-testid="wandb-state"
        data-wandb-enabled={metrics.wandbEnabled}
      >
        {metrics.wandbEnabled ? "W&B 활성" : "W&B 비활성 — 로컬 로그에서 렌더"}
      </p>

      <label className="oa-trn__field">
        <span>지표</span>
        <select
          value={key}
          data-testid="metric-select"
          onChange={(event) => setSelectedKey(event.target.value as MetricKey)}
        >
          {METRIC_KEYS.map((metricKey) => (
            <option key={metricKey} value={metricKey}>
              {metricMeta(metricKey).label}
            </option>
          ))}
        </select>
      </label>

      <svg
        className="oa-trn__chart"
        viewBox={`0 0 ${PLOT_WIDTH} ${PLOT_HEIGHT}`}
        role="img"
        aria-label={`${meta.label} 곡선`}
        data-testid="loss-curve-svg"
        data-metric={key}
        data-points={points.length}
      >
        <polyline fill="none" className="oa-trn__chart-line" points={line} data-testid="loss-curve-line" />
      </svg>

      <p className="oa-trn__chart-readout" data-testid="metric-readout">
        {latest !== null
          ? `step ${latest.step}: ${latest.value} ${meta.unit}`.trim()
          : "샘플 없음"}
      </p>

      <pre className="oa-trn__log" data-testid="log-tail">
        {metrics.logTail.join("\n")}
      </pre>
    </section>
  );
}
