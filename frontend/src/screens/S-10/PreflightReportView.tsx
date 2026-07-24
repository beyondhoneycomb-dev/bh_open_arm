// The dataset-preflight report renderer (WP-4A-02, CG-G-S10 facade). It renders the
// backend `PreflightReport` verbatim: the PASS/BLOCK verdict and, for a BLOCK, each
// located finding — its code, the channel, and for a state-channel fault the joint and
// per-motor component. It recomputes nothing: "training config invalid" cannot tell an
// operator whether to fix the recording, the rename map or the statistics, so the screen
// shows exactly what the backend located and no more.

import type { PreflightReport } from "./types";

export interface PreflightReportViewProps {
  report: PreflightReport;
}

export function PreflightReportView({ report }: PreflightReportViewProps) {
  return (
    <section
      className="oa-trn__panel"
      aria-labelledby="oa-trn-preflight-title"
      data-testid="preflight-report"
    >
      <h2 id="oa-trn-preflight-title" className="oa-trn__section-title">
        데이터셋 프리플라이트
      </h2>

      <p
        className="oa-trn__verdict"
        data-testid="preflight-verdict"
        data-verdict={report.verdict}
      >
        판정: {report.verdict}
      </p>

      {report.findings.length > 0 && (
        <ul className="oa-trn__findings" data-testid="preflight-findings">
          {report.findings.map((finding, index) => (
            <li key={`${finding.code}-${finding.channelName}-${index}`} className="oa-trn__finding">
              <span className="oa-trn__finding-code">{finding.code}</span>
              <span className="oa-trn__finding-loc">
                {finding.channelName}
                {finding.joint !== null && ` · ${finding.joint}`}
                {finding.component !== null && `${finding.component}`}
              </span>
              <span className="oa-trn__finding-detail">{finding.detail}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
