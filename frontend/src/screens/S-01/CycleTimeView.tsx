// The loop cycle-time p95 tile (FR-GUI-100 / NFR-GUI-011). Its source is the
// PG-RT-001b artifact and nothing else: never self-measured, never the provisional
// Wave-1 figure that PG-RT-001b can supersede (CG-G-S01d / CG-5-02d). The
// provenance is shown so a reader knows which artifact the number is. When the
// artifact has not landed — as on this offline box — the tile reads UNAVAILABLE,
// never OK and never a fabricated number (CG-G-S01e).
//
// On a WARN (the backend decided the loop ran under target for N consecutive
// cycles), the tile shows the FOUR-way cause split — CAN, camera grab+encode, IK,
// WS serialization — each channel's own contribution, OR the backend's explicit
// "unimplemented" note. It never shows a bare total that hides which channel is
// the cost (CG-5-02e). The screen renders whichever the backend supplied; it
// splits nothing itself.

import type { CycleTime, CycleWarnDetail } from "./types";

interface CycleTimeViewProps {
  cycleTime: CycleTime;
}

function WarnDetail({ detail }: { detail: CycleWarnDetail }) {
  if (detail.kind === "unimplemented") {
    return (
      <p className="oa-dash__cycle-cause" data-testid="cycle-cause-unimplemented" role="status">
        원인 구간 분해 미구현 — {detail.note}
      </p>
    );
  }
  return (
    <ul className="oa-dash__cycle-cause" data-testid="cycle-cause-breakdown" data-cause-count="4">
      <li data-testid="cycle-cause-can">CAN: {detail.canMs} ms</li>
      <li data-testid="cycle-cause-camera">카메라 grab·인코딩: {detail.cameraGrabEncodeMs} ms</li>
      <li data-testid="cycle-cause-ik">IK: {detail.ikMs} ms</li>
      <li data-testid="cycle-cause-ws">WS 직렬화: {detail.wsSerializationMs} ms</li>
      <li data-testid="cycle-cause-cycles">연속 미달 사이클: {detail.consecutiveCycles}</li>
    </ul>
  );
}

export function CycleTimeView({ cycleTime }: CycleTimeViewProps) {
  return (
    <section className="oa-dash__panel" aria-labelledby="oa-dash-cycle-title">
      <h2 id="oa-dash-cycle-title" className="oa-dash__panel-title">
        제어 루프 사이클 타임 p95
      </h2>
      {cycleTime.available ? (
        <div
          className="oa-dash__tile"
          data-testid="fr100-cycle-p95"
          data-render-state={cycleTime.warn === null ? "OK" : "WARN"}
        >
          <span className="oa-dash__tile-value" data-testid="cycle-p95">
            p95 {cycleTime.p95Ms} ms
          </span>
          <span className="oa-dash__tile-sub" data-testid="cycle-percentiles">
            p50 {cycleTime.p50Ms} ms · p99 {cycleTime.p99Ms} ms · 목표 {cycleTime.targetDisplay}
          </span>
          <span className="oa-dash__tile-source" data-testid="cycle-source">
            출처: {cycleTime.source}
          </span>
          {cycleTime.warn === null ? null : <WarnDetail detail={cycleTime.warn} />}
        </div>
      ) : (
        <div
          className="oa-dash__tile oa-dash__state--unavailable"
          data-testid="fr100-cycle-p95"
          data-render-state="UNAVAILABLE"
        >
          <span className="oa-dash__tile-value" data-testid="cycle-unavailable">
            미가용 (UNAVAILABLE)
          </span>
          <span className="oa-dash__tile-sub">{cycleTime.reason}</span>
          <span className="oa-dash__tile-source" data-testid="cycle-source">
            출처: {cycleTime.source}
          </span>
        </div>
      )}
    </section>
  );
}
