// The C-Lat (control-channel latency) measurement view (CG-G-S05a, FR-GUI-106,
// NFR-PRF-014/018, `05` §2.5). C-Lat is the control channel ONLY — controller
// physical move to motor axis reaction — and the one thing software cannot measure
// is the latency INSIDE the headset before a pose is emitted. That limit is a
// standing note this view carries at all times: without it an operator reads C-Lat
// as the whole glass-to-glass loop, which it is not.
//
// Every stage value here is a backend reading (measured / computed / unknown /
// eliminated / design-variable); the view renders the distinction rather than
// flattening it to one number, and computes no latency itself.

import type { CLatStage, CLatStageKind, CLatStatus } from "./teleopSource";

// The standing note CG-G-S05a requires beside the C-Lat display. It is a fixed fact
// about what the control channel cannot see, not a backend value.
export const HEADSET_INTERNAL_LATENCY_NOTE =
  "헤드셋 내부 지연 미포함 — C-Lat은 제어채널 지연일 뿐이며 헤드셋 내부 지연은 소프트웨어로 측정 불가";

const KIND_LABELS: Readonly<Record<CLatStageKind, string>> = {
  measured: "측정",
  computed: "계산",
  unknown: "미확인",
  eliminated: "소멸",
  design_variable: "설계 변수",
};

function stageValueText(stage: CLatStage): string {
  if (stage.kind === "eliminated") {
    return "≈ 0 ms";
  }
  if (stage.valueMs === null) {
    return "[미측정]";
  }
  return `${stage.valueMs.toFixed(stage.valueMs < 1 ? 3 : 1)} ms`;
}

interface CLatViewProps {
  cLat: CLatStatus;
}

export function CLatView({ cLat }: CLatViewProps) {
  return (
    <section className="oa-tel__clat" aria-label="C-Lat 제어채널 지연">
      <h2 className="oa-tel__h2">C-Lat (제어채널 지연)</h2>

      <p className="oa-tel__clat-note" role="note" data-field="headset-internal-note">
        {HEADSET_INTERNAL_LATENCY_NOTE}
      </p>

      <div className="oa-tel__clat-totals">
        <span data-field="clat-lower-bound">
          하한(백엔드 자체 산출): {cLat.lowerBoundMs.toFixed(1)} ms
        </span>
        <span data-field="clat-p50">
          총 p50: {cLat.totalP50Ms === null ? "[미측정]" : `${cLat.totalP50Ms.toFixed(1)} ms`}
        </span>
        <span data-field="clat-p99">
          총 p99: {cLat.totalP99Ms === null ? "[미측정]" : `${cLat.totalP99Ms.toFixed(1)} ms`}
        </span>
      </div>

      <ol className="oa-tel__clat-stages" aria-label="C-Lat 스테이지 예산">
        {cLat.stages.map((stage) => (
          <li key={stage.marker} className="oa-tel__clat-stage" data-kind={stage.kind}>
            <span className="oa-tel__clat-marker">{stage.marker}</span>
            <span className="oa-tel__clat-label">{stage.label}</span>
            <span className="oa-tel__clat-value">{stageValueText(stage)}</span>
            <span className="oa-tel__clat-kind">{KIND_LABELS[stage.kind]}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
