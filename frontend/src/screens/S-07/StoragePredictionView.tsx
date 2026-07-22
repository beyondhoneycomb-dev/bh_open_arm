// The storage prediction panel (CG-G-S07g). It renders the backend disk watch's
// figures — free space, fill rate, and predicted recordable headroom — and shows
// whether the start is blocked below the one-hour floor. The prediction is the
// backend's (WP-3B-12 diskwatch / WP-3C-02); the view computes nothing, it reads
// `headroomHours` and compares it to the shared DISK_MIN_HEADROOM_HOURS constant.

import { DISK_MIN_HEADROOM_HOURS } from "../../global";
import { storageHeadroomOk } from "./startGate";
import type { StoragePrediction } from "./types";

export interface StoragePredictionViewProps {
  storage: StoragePrediction;
}

const BYTES_PER_GIB = 1024 * 1024 * 1024;

function gib(bytes: number): string {
  return `${(bytes / BYTES_PER_GIB).toFixed(1)} GiB`;
}

export function StoragePredictionView({ storage }: StoragePredictionViewProps) {
  const headroomOk = storageHeadroomOk(storage);
  return (
    <section
      className="oa-collect__storage"
      aria-labelledby="oa-collect-storage-title"
      data-testid="storage-prediction"
    >
      <h2 id="oa-collect-storage-title" className="oa-collect__section-title">
        저장량 예측
      </h2>
      <dl className="oa-collect__storage-grid">
        <div className="oa-collect__storage-row">
          <dt>디스크 여유</dt>
          <dd>
            {gib(storage.freeBytes)} / {gib(storage.totalBytes)}
          </dd>
        </div>
        <div className="oa-collect__storage-row">
          <dt>기록 속도</dt>
          <dd>{gib(storage.bytesPerHour)} / 시간</dd>
        </div>
        <div className="oa-collect__storage-row">
          <dt>예상 여유 시간</dt>
          <dd data-testid="storage-headroom">{storage.headroomHours.toFixed(2)} 시간</dd>
        </div>
      </dl>
      {!headroomOk && (
        <p className="oa-collect__storage-block" role="alert" data-testid="storage-block">
          디스크 여유가 {DISK_MIN_HEADROOM_HOURS}시간 미만입니다 — 수집 시작이 차단됩니다.
        </p>
      )}
    </section>
  );
}
