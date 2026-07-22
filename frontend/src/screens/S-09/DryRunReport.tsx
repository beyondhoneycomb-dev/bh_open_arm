// CG-G-S09d: the dry-run's six checks (position / velocity / torque / cell-collision
// / self-collision / lifter, FR-SIM-030) render PER ITEM with their verdict and any
// violation detail, and the real-send UI is HARD-BLOCKED until all six pass
// (FR-SIM-033). The report and every violation number come from the backend MuJoCo
// dry-run; this view renders them and gates the send. A bypass exists but only
// behind an explicit confirmation — a hard gate, not a suggestion.

import { useState } from "react";

import {
  DRY_RUN_CHECKS,
  DRY_RUN_CHECK_COUNT,
  allChecksPassed,
  orderedCheckResults,
  type ControlTarget,
  type DryRunCheckStatus,
  type DryRunReport as DryRunReportData,
} from "./simDomain";

interface DryRunReportProps {
  report: DryRunReportData | null;
  controlTarget: ControlTarget;
  onSendToReal: () => void;
}

const STATUS_LABELS: Readonly<Record<DryRunCheckStatus, string>> = {
  pass: "통과",
  fail: "실패",
  not_run: "미실행",
};

const CHECK_LABELS = new Map(DRY_RUN_CHECKS.map((meta) => [meta.id, meta.label]));

export function DryRunReport({ report, controlTarget, onSendToReal }: DryRunReportProps) {
  const [overrideConfirmed, setOverrideConfirmed] = useState<boolean>(false);

  const results = orderedCheckResults(report);
  const passed = allChecksPassed(report);
  const targetingReal = controlTarget === "real";

  return (
    <section className="oa-sim__dryrun" aria-labelledby="oa-sim-dryrun-title">
      <h2 id="oa-sim-dryrun-title" className="oa-sim__section-title">
        드라이런 6검사
      </h2>

      <ul className="oa-sim__dryrun-list" aria-label={`드라이런 검사 ${DRY_RUN_CHECK_COUNT}항목`}>
        {results.map((result) => (
          <li
            key={result.id}
            className="oa-sim__dryrun-item"
            data-check={result.id}
            data-status={result.status}
          >
            <div className="oa-sim__dryrun-item-head">
              <span className="oa-sim__dryrun-item-label">{CHECK_LABELS.get(result.id)}</span>
              <span className={`oa-sim__dryrun-status oa-sim__dryrun-status--${result.status}`}>
                {STATUS_LABELS[result.status]}
              </span>
            </div>
            {result.violation && (
              <p className="oa-sim__dryrun-violation">
                {`관절 ${result.violation.joint} · t=${result.violation.simTimeS}s · 초과 ${result.violation.overshoot}`}
              </p>
            )}
          </li>
        ))}
      </ul>

      <div className="oa-sim__send">
        {!passed && (
          <p className="oa-sim__send-block" role="alert">
            드라이런 미통과 — 실기 전송 하드 차단 (FR-SIM-033).
          </p>
        )}
        <button
          type="button"
          className="oa-sim__send-btn"
          onClick={onSendToReal}
          disabled={!passed || !targetingReal}
          aria-disabled={!passed || !targetingReal}
        >
          실기 전송
        </button>

        {!passed && (
          <details className="oa-sim__send-override">
            <summary>게이트 우회 (명시 확인 필요)</summary>
            <label className="oa-sim__send-override-confirm">
              <input
                type="checkbox"
                checked={overrideConfirmed}
                onChange={(event) => setOverrideConfirmed(event.target.checked)}
              />
              드라이런 미통과 상태로 전송함을 확인한다.
            </label>
            <button
              type="button"
              className="oa-sim__send-override-btn"
              onClick={onSendToReal}
              disabled={!overrideConfirmed || !targetingReal}
              aria-disabled={!overrideConfirmed || !targetingReal}
            >
              우회 전송 (확인됨)
            </button>
          </details>
        )}
      </div>
    </section>
  );
}
