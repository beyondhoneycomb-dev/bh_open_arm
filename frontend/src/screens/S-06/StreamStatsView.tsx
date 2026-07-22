// The stream-stats table: FPS / jitter_ms / drop for every instrumented channel,
// with a WARN badge when achieved FPS falls under 95% of target or the record
// drop fraction exceeds 2% (CG-G-S06e). The three metrics come from the shared WS
// StreamMeter and the backend DropReport; the screen renders the NFR-CAM-006
// comparison and owns neither the target nor the pass verdict.

import { evaluateStream, type StreamMetricView } from "./metrics";
import type { CameraRuntime } from "./source";

interface StreamStatsViewProps {
  cameras: Readonly<Record<string, CameraRuntime>>;
}

function metricRows(cameras: Readonly<Record<string, CameraRuntime>>): StreamMetricView[] {
  const rows: StreamMetricView[] = [];
  for (const runtime of Object.values(cameras)) {
    rows.push(evaluateStream(runtime.rgbStats, runtime.fps, runtime.recordDropFraction));
    if (runtime.depthStats !== null) {
      rows.push(evaluateStream(runtime.depthStats, runtime.fps, runtime.recordDropFraction));
    }
  }
  return rows;
}

function levelLabel(level: StreamMetricView["level"]): string {
  if (level === "warn") {
    return "WARN";
  }
  return level === "unknown" ? "미구성" : "OK";
}

export function StreamStatsView({ cameras }: StreamStatsViewProps) {
  const rows = metricRows(cameras);
  return (
    <section className="oa-cam__panel" aria-labelledby="oa-cam-stats-title">
      <h2 id="oa-cam-stats-title" className="oa-cam__panel-title">
        스트림 통계 (FPS · jitter_ms · 드롭)
      </h2>
      <table className="oa-cam__stats">
        <thead>
          <tr>
            <th scope="col">채널</th>
            <th scope="col">FPS</th>
            <th scope="col">목표</th>
            <th scope="col">jitter_ms</th>
            <th scope="col">드롭(meter)</th>
            <th scope="col">기록 드롭률</th>
            <th scope="col">상태</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.channel} data-metric-channel={row.channel} data-metric-level={row.level}>
              <td className="oa-cam__stats-key">{row.channel}</td>
              <td>{row.fps.toFixed(1)}</td>
              <td>{row.targetFps === null ? "—" : row.targetFps.toFixed(0)}</td>
              <td>{row.jitterMs.toFixed(1)}</td>
              <td>{row.dropCount}</td>
              <td>{(row.recordDropFraction * 100).toFixed(1)}%</td>
              <td>
                <span className={`oa-cam__level oa-cam__level--${row.level}`}>
                  {levelLabel(row.level)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
