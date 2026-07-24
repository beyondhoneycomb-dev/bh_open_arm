// The capture-jitter view (CG-G-S08c). Real capture jitter is read ONLY from the
// per-slot capture_ts sidecar — the nanosecond grab instants the backend logged. The
// synthetic `timestamp` grid (frame_index / fps) is perfectly even, so reading jitter
// off it would show a flat zero forever; this view never touches that grid. The
// interval-spread figures come from `jitterForSidecars`, which differences the
// sidecar's capture instants.

import { jitterForSidecars } from "./jitter";
import type { CaptureTsSidecar } from "./types";

export interface CaptureJitterViewProps {
  sidecars: readonly CaptureTsSidecar[];
}

export function CaptureJitterView({ sidecars }: CaptureJitterViewProps) {
  const stats = jitterForSidecars(sidecars);
  return (
    <section className="oa-ds__jitter" aria-labelledby="oa-ds-jitter-title">
      <h2 id="oa-ds-jitter-title" className="oa-ds__section-title">
        캡처 지터
      </h2>
      <p className="oa-ds__jitter-note" data-testid="jitter-source-note">
        캡처 지터는 사이드카 capture_ts(실제 grab 시각)에서 계산합니다 — 합성 timestamp
        그리드가 아닙니다.
      </p>
      <table className="oa-ds__jitter-table">
        <thead>
          <tr>
            <th scope="col">슬롯</th>
            <th scope="col">프레임</th>
            <th scope="col">평균 간격</th>
            <th scope="col">지터 (max−min)</th>
          </tr>
        </thead>
        <tbody>
          {stats.map((stat) => (
            <tr key={stat.slot} data-testid={`jitter-${stat.slot}`}>
              <td>{stat.slot}</td>
              <td>{stat.sampleCount}</td>
              <td>{stat.meanIntervalMs.toFixed(2)} ms</td>
              <td data-testid={`jitter-value-${stat.slot}`}>{stat.jitterMs.toFixed(2)} ms</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
