// The One-Euro smoother parameter form (CG-G-S05d, FR-GUI-106, `05` §3 filter row).
// min_cutoff / beta / d_cutoff are exposed as runtime settings, and the theoretical
// phase lag `tau = 1/(2π·f_c)` is shown alongside min_cutoff. The tau VALUE is the
// backend's applied figure (`SmootherApplied.tauMs`, NFR-PRF-018) — the screen shows
// the formula LABEL and the backend value, it derives no tau itself; the form ships
// the requested values and the backend applies/echoes them.
//
// The spec is explicit that this theoretical tau is NOT the measured phase lag (the
// One-Euro cutoff is speed-dependent), so the label marks it as theoretical and the
// measured figure lives in the C-Lat view, not here.

import { useState } from "react";

import type { SmootherStatus } from "./teleopSource";

// The FR-GUI-106 formula shown alongside the min_cutoff control. A documentation
// string, not a computation.
export const PHASE_LAG_FORMULA = "τ = 1/(2π·f_c)";

interface SmootherParamFormProps {
  smoother: SmootherStatus;
  disabled: boolean;
  onChange: (minCutoffHz: number, beta: number, dCutoff: number) => void;
}

export function SmootherParamForm({ smoother, disabled, onChange }: SmootherParamFormProps) {
  const { applied } = smoother;
  const [minCutoff, setMinCutoff] = useState(applied.minCutoffHz);
  const [beta, setBeta] = useState(applied.beta);
  const [dCutoff, setDCutoff] = useState(applied.dCutoff);

  function emit(nextMinCutoff: number, nextBeta: number, nextDCutoff: number): void {
    onChange(nextMinCutoff, nextBeta, nextDCutoff);
  }

  return (
    <section className="oa-tel__smoother" aria-label="One-Euro 스무더 파라미터">
      <h2 className="oa-tel__h2">One-Euro 스무더</h2>

      <div className="oa-tel__param">
        <label htmlFor="oa-tel-min-cutoff">min_cutoff (Hz)</label>
        <input
          id="oa-tel-min-cutoff"
          type="range"
          data-field="min-cutoff"
          min={smoother.minCutoffMin}
          max={smoother.minCutoffMax}
          step={0.1}
          value={minCutoff}
          disabled={disabled}
          onChange={(event) => {
            const next = Number(event.target.value);
            setMinCutoff(next);
            emit(next, beta, dCutoff);
          }}
        />
        <output data-field="min-cutoff-value">{minCutoff.toFixed(2)} Hz</output>
        <p className="oa-tel__tau" data-field="phase-lag">
          이론 위상 지연 {PHASE_LAG_FORMULA} ≈{" "}
          <span data-field="tau-applied">{applied.tauMs.toFixed(1)} ms</span>{" "}
          (적용값 f_c={applied.minCutoffHz.toFixed(2)} Hz, 백엔드 산출 · 실측 아님)
        </p>
      </div>

      <div className="oa-tel__param">
        <label htmlFor="oa-tel-beta">beta</label>
        <input
          id="oa-tel-beta"
          type="range"
          data-field="beta"
          min={smoother.betaMin}
          max={smoother.betaMax}
          step={0.01}
          value={beta}
          disabled={disabled}
          onChange={(event) => {
            const next = Number(event.target.value);
            setBeta(next);
            emit(minCutoff, next, dCutoff);
          }}
        />
        <output data-field="beta-value">{beta.toFixed(2)}</output>
      </div>

      <div className="oa-tel__param">
        <label htmlFor="oa-tel-d-cutoff">d_cutoff (Hz)</label>
        <input
          id="oa-tel-d-cutoff"
          type="range"
          data-field="d-cutoff"
          min={smoother.dCutoffMin}
          max={smoother.dCutoffMax}
          step={0.1}
          value={dCutoff}
          disabled={disabled}
          onChange={(event) => {
            const next = Number(event.target.value);
            setDCutoff(next);
            emit(minCutoff, beta, next);
          }}
        />
        <output data-field="d-cutoff-value">{dCutoff.toFixed(2)} Hz</output>
      </div>

      <p className="oa-tel__hint">
        min_cutoff↑ → 위상 지연↓ (지터↑). 실측 C-Lat은 속도 종속이라 이 이론값과 다르다 — 실측은 C-Lat 뷰.
      </p>
    </section>
  );
}
