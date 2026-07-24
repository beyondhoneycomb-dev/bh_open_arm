// The integrity verification report (WP-3D-05). The verdict (READY / INVALID), the
// per-check pass/fail results, and the missing-check list are all the BACKEND
// verifier's — the screen renders them and recomputes nothing. A missing check is
// shown as loudly as a failed one, because a dataset is READY only when the whole
// required check set ran and passed; a UI that quietly treated an absent check as a
// pass could certify a dataset the verifier never fully examined.

import type { VerificationReport } from "./types";

export interface VerificationReportViewProps {
  report: VerificationReport;
}

export function VerificationReportView({ report }: VerificationReportViewProps) {
  return (
    <section className="oa-ds__verify" aria-labelledby="oa-ds-verify-title">
      <h2 id="oa-ds-verify-title" className="oa-ds__section-title">
        검증 리포트
      </h2>

      <p className="oa-ds__verify-verdict" data-testid="verify-verdict" data-verdict={report.verdict}>
        {report.verdict === "READY" ? "READY — 학습 입력 가능" : "INVALID — 학습 입력 불가"}
      </p>

      <ul className="oa-ds__verify-list">
        {report.results.map((result) => (
          <li
            key={result.name}
            className="oa-ds__verify-row"
            data-status={result.status}
            data-testid={`check-${result.name}`}
          >
            <span className="oa-ds__verify-mark" aria-hidden="true">
              {result.status === "pass" ? "✓" : "✗"}
            </span>
            <span className="oa-ds__verify-name">{result.name}</span>
            <span className="oa-ds__verify-detail">{result.detail}</span>
          </li>
        ))}
      </ul>

      {report.missingChecks.length > 0 && (
        <p className="oa-ds__verify-missing" role="alert" data-testid="verify-missing">
          미실행 검사: {report.missingChecks.join(", ")} — 누락은 실패와 동일하게 INVALID
        </p>
      )}
    </section>
  );
}
