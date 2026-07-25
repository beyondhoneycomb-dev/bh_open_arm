// The per-target block matrix + IK-gate view (CG-G-S11g/h, PG-IK-001). It renders the
// committed WP-4B-04 fleet verdicts across all four targets: the expected inference
// frequency and its source, which backends and optimizations each cell blocks, and each
// target's IK-gate support label. Selecting a target switches which verdict the mode
// selector gates against. This view decides nothing — a target reads unsupported only
// because its verdict's IK gate is `fail_blocking` (the backend's fact), and sync reads
// blocked only because the verdict blocked it.

import type { DeploymentTarget, TargetPolicyVerdict } from "./types";
import { targetSupport } from "./deployVerdict";

export interface DeployMatrixViewProps {
  fleetVerdicts: readonly TargetPolicyVerdict[];
  selectedTarget: DeploymentTarget;
  onSelectTarget: (target: DeploymentTarget) => void;
  // Target selection emits a command frame, so it is a control affordance and obeys the
  // schema lock like every other one (CG-G-S11a): disabled on a version skew so no frame
  // leaks past the lock. Defaults false so a caller that forgets to wire it stays safe-open
  // (the screen always passes the real lock state).
  disabled?: boolean;
}

export function DeployMatrixView({
  fleetVerdicts,
  selectedTarget,
  onSelectTarget,
  disabled = false,
}: DeployMatrixViewProps) {
  return (
    <section className="oa-inf__matrix" aria-labelledby="oa-inf-matrix-title" data-testid="deploy-matrix">
      <h2 id="oa-inf-matrix-title" className="oa-inf__section-title">
        배포 타깃 매트릭스
      </h2>
      <div className="oa-inf__matrix-scroll">
        <table className="oa-inf__matrix-table">
          <thead>
            <tr>
              <th scope="col">타깃</th>
              <th scope="col">예상 Hz</th>
              <th scope="col">차단 백엔드</th>
              <th scope="col">차단 최적화</th>
              <th scope="col">IK 게이트</th>
            </tr>
          </thead>
          <tbody>
            {fleetVerdicts.map((verdict) => {
              const support = targetSupport(verdict);
              const selected = verdict.target === selectedTarget;
              return (
                <tr
                  key={verdict.target}
                  data-testid={`target-row-${verdict.target}`}
                  data-selected={selected}
                >
                  <th scope="row">
                    <button
                      type="button"
                      className="oa-inf__target-select"
                      aria-pressed={selected}
                      disabled={disabled}
                      data-testid={`target-select-${verdict.target}`}
                      onClick={() => onSelectTarget(verdict.target)}
                    >
                      {verdict.target}
                    </button>
                  </th>
                  <td data-testid={`target-hz-${verdict.target}`}>
                    {verdict.expectedHz === null ? "미상 (self-bench)" : `${verdict.expectedHz} Hz`}
                  </td>
                  <td data-testid={`target-blocked-backends-${verdict.target}`}>
                    {verdict.blockedBackends.length === 0 ? "—" : verdict.blockedBackends.join(", ")}
                  </td>
                  <td data-testid={`target-blocked-opts-${verdict.target}`}>
                    {verdict.blockedOptimizations.length === 0
                      ? "—"
                      : verdict.blockedOptimizations.join(", ")}
                  </td>
                  <td
                    className="oa-inf__support"
                    data-testid={`target-support-${verdict.target}`}
                    data-support={support.supported}
                    title={support.note}
                  >
                    {support.label}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
