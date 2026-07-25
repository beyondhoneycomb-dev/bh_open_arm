// The resource tiles of FR-GUI-100: disk free + projected exhaustion time, and
// GPU/VRAM. Every value is backend-formatted (free-space string, exhaustion date,
// VRAM "used / total" string) so the dashboard shows no arithmetic. A null
// exhaustion projection or an absent GPU renders as an explicit unavailable label,
// never a fabricated number and never a blank that reads OK (CG-G-S01e).

import { RENDER_STATE_CLASS, RENDER_STATE_LABEL } from "./severity";
import type { DiskStatus, GpuStatus } from "./types";
import { UNAVAILABLE } from "./types";

interface ResourceViewProps {
  disk: DiskStatus;
  gpu: GpuStatus;
}

export function ResourceView({ disk, gpu }: ResourceViewProps) {
  const diskState = disk.state ?? UNAVAILABLE;
  const gpuState = gpu.present ? gpu.state ?? UNAVAILABLE : UNAVAILABLE;
  return (
    <section className="oa-dash__panel" aria-labelledby="oa-dash-res-title">
      <h2 id="oa-dash-res-title" className="oa-dash__panel-title">
        디스크 · GPU
      </h2>

      <div
        className={`oa-dash__tile ${RENDER_STATE_CLASS[diskState]}`}
        data-testid="fr100-disk"
        data-render-state={diskState}
      >
        <span className="oa-dash__tile-label">디스크 여유</span>
        <span className="oa-dash__tile-value">{disk.freeDisplay}</span>
        <span className="oa-dash__tile-sub" data-testid="disk-exhaustion">
          예상 소진 시각: {disk.exhaustionDisplay ?? "예측 불가"}
        </span>
        <span className="oa-dash__tile-state">{RENDER_STATE_LABEL[diskState]}</span>
      </div>

      <div
        className={`oa-dash__tile ${RENDER_STATE_CLASS[gpuState]}`}
        data-testid="fr100-gpu"
        data-render-state={gpuState}
      >
        <span className="oa-dash__tile-label">GPU · VRAM</span>
        {gpu.present ? (
          <>
            <span className="oa-dash__tile-value">{gpu.name}</span>
            <span className="oa-dash__tile-sub" data-testid="gpu-vram">
              VRAM {gpu.vramDisplay} · 사용률 {gpu.utilizationDisplay} · {gpu.temperatureDisplay}
            </span>
          </>
        ) : (
          <span className="oa-dash__tile-value" data-testid="gpu-absent">
            GPU 미탑재
          </span>
        )}
        <span className="oa-dash__tile-state">{RENDER_STATE_LABEL[gpuState]}</span>
      </div>
    </section>
  );
}
