// CG-G-S09b: twin and dry-run may start only when the real arm is on the `stiff`
// (230-series) gain profile; attempting to start on `compliant` (70-series) is
// REFUSED. FR-SIM-028b is the frozen precondition — the MJCF is modelled stiff, so
// any other profile splits sim/real response and contaminates the residual. The
// backend enforces this; the screen gates the UI so the operator cannot even try,
// and shows why. The gate reads the backend gain profile; it decides no threshold.

import {
  GAIN_PARITY_REFUSAL_REASON,
  GAIN_PROFILES,
  twinDryRunAllowed,
  type GainProfile,
} from "./simDomain";

interface GainParityGateProps {
  gainProfile: GainProfile;
  onStartTwin: () => void;
  onStartDryRun: () => void;
}

export function GainParityGate({
  gainProfile,
  onStartTwin,
  onStartDryRun,
}: GainParityGateProps) {
  const allowed = twinDryRunAllowed(gainProfile);

  return (
    <section className="oa-sim__gain" aria-labelledby="oa-sim-gain-title">
      <h2 id="oa-sim-gain-title" className="oa-sim__section-title">
        게인 패리티
      </h2>

      <p className="oa-sim__gain-active" role="status">
        실기 PD 게인 프로파일: <strong>{GAIN_PROFILES[gainProfile].label}</strong>
      </p>

      {!allowed && (
        <p className="oa-sim__gain-refusal" role="alert">
          {GAIN_PARITY_REFUSAL_REASON}
        </p>
      )}

      <div className="oa-sim__gain-actions">
        <button
          type="button"
          onClick={onStartTwin}
          disabled={!allowed}
          aria-disabled={!allowed}
        >
          디지털 트윈 시작
        </button>
        <button
          type="button"
          onClick={onStartDryRun}
          disabled={!allowed}
          aria-disabled={!allowed}
        >
          드라이런 시작
        </button>
      </div>
    </section>
  );
}
