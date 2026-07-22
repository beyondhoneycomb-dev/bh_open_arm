// Renders a backend trajectory pre-verification report (FR-MAN-044). The verdict
// and each item come from the MAN domain; this component only displays them, and
// the caller uses report.passed to disable execute (CG-G-S04h). It states the
// first violating waypoint so a failure is actionable rather than opaque.

import type { PreVerifyReport as PreVerifyReportData } from "./manualSource";

export interface PreVerifyReportProps {
  report: PreVerifyReportData;
  label: string;
}

export function PreVerifyReport({ report, label }: PreVerifyReportProps) {
  return (
    <div
      className="oa-man-preverify"
      data-field="preverify"
      data-passed={report.passed ? "true" : "false"}
    >
      <p className="oa-man-preverify__label">
        {label}: {report.passed ? "통과" : "실패"}
      </p>
      {!report.passed && report.firstViolationIndex !== null && (
        <p className="oa-man-preverify__first" role="alert">
          최초 위반 웨이포인트: #{report.firstViolationIndex}
        </p>
      )}
      <ul className="oa-man-preverify__checks">
        {report.checks.map((check) => (
          <li key={check.id} data-check={check.id} data-check-passed={check.passed ? "true" : "false"}>
            {check.label}: {check.passed ? "OK" : "위반"}
            {check.detail && <span> — {check.detail}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}
