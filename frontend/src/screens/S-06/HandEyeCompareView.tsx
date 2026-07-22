// The hand-eye five-method compare view (CG-G-S06f). `06` FR-CAM-026 forbids a
// single-method result, so this view renders ALL five methods and their pairwise
// deviations side by side and offers NO control to adopt one — an outlier is made
// visible, never silently chosen. The residuals and deviations are backend facts;
// the screen selects nothing.

import {
  hasAllMethods,
  maxRotationDeviationDeg,
  maxTranslationDeviationMm,
  type HandEyeView,
} from "./handEye";

interface HandEyeCompareViewProps {
  results: readonly HandEyeView[];
}

function setupLabel(setup: HandEyeView["setup"]): string {
  return setup === "eye_in_hand" ? "eye-in-hand (손목)" : "eye-to-hand (고정)";
}

function CalibrationCard({ view }: { view: HandEyeView }) {
  return (
    <article className="oa-cam__handeye-card" data-handeye-slot={view.slot}>
      <header className="oa-cam__handeye-head">
        <span className="oa-cam__handeye-slot">{view.slot}</span>
        <span className="oa-cam__handeye-setup">{setupLabel(view.setup)}</span>
        <span className="oa-cam__handeye-poses">{view.samplePoseCount} 포즈</span>
        {view.stale ? (
          <span className="oa-cam__badge oa-cam__badge--stale" data-handeye-stale="true">
            STALE
          </span>
        ) : null}
      </header>
      <table className="oa-cam__handeye-table">
        <thead>
          <tr>
            <th scope="col">메서드</th>
            <th scope="col">회전 잔차(°)</th>
            <th scope="col">병진 잔차(mm)</th>
          </tr>
        </thead>
        <tbody>
          {view.methods.map((row) => (
            <tr key={row.method} data-handeye-method={row.method}>
              <td className="oa-cam__stats-key">{row.method}</td>
              <td>{row.residualRotationDeg.toFixed(2)}</td>
              <td>{row.residualTranslationMm.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="oa-cam__handeye-agreement" data-handeye-agreement={view.slot}>
        최대 상호편차: 회전 {maxRotationDeviationDeg(view).toFixed(2)}° · 병진{" "}
        {maxTranslationDeviationMm(view).toFixed(2)} mm
      </p>
      {hasAllMethods(view) ? null : (
        <p className="oa-cam__handeye-warn" role="status">
          5메서드 미완 — 결과를 채택하지 마십시오
        </p>
      )}
    </article>
  );
}

export function HandEyeCompareView({ results }: HandEyeCompareViewProps) {
  return (
    <section className="oa-cam__panel" aria-labelledby="oa-cam-handeye-title">
      <h2 id="oa-cam-handeye-title" className="oa-cam__panel-title">
        hand-eye 5메서드 병렬 비교
      </h2>
      <p className="oa-cam__panel-note">
        FR-CAM-026: 다섯 메서드를 동시에 제시한다. 단일 메서드 채택 UI는 없다 — 상호편차를 읽고
        판단한다.
      </p>
      {results.length === 0 ? (
        <p className="oa-cam__empty" role="status">
          hand-eye 결과 없음
        </p>
      ) : (
        <div className="oa-cam__handeye-grid">
          {results.map((view) => (
            <CalibrationCard key={view.slot} view={view} />
          ))}
        </div>
      )}
    </section>
  );
}
