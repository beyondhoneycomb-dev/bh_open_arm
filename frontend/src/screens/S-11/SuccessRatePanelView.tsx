// The success-rate panel (CG-G-S11b/c, the 4C increment). It renders the WP-4C-03 report
// through the `describeSuccessRate` display, which is the only source of the point estimate
// and always carries the Wilson 95% CI. Three rules are visible here:
//   - the point estimate is NEVER shown alone: it and the Wilson CI live in one element
//     (`data-testid="success-rate"`), so a reader cannot see 60% without seeing its ±width;
//   - N < 20 shows the statistically-meaningless flag and suppresses ranking (`rankingAllowed`);
//   - during the 4B->4C landing window the report is null, so this panel shows NO number —
//     an explicit awaiting-aggregation state, never a placeholder rate (the 2-landing note).
// The panel reads the co-recorded items (collision, latency, ...) straight off the report,
// but never touches `pointEstimate` — that field is read only in successRate.ts.

import type { SuccessRateReport } from "./types";
import type { SuccessRateDisplay } from "./successRate";

export interface SuccessRatePanelViewProps {
  display: SuccessRateDisplay | null;
  report: SuccessRateReport | null;
}

export function SuccessRatePanelView({ display, report }: SuccessRatePanelViewProps) {
  return (
    <section className="oa-inf__success" aria-labelledby="oa-inf-success-title" data-testid="success-rate-panel">
      <h2 id="oa-inf-success-title" className="oa-inf__section-title">
        성공률 (Wilson 95% CI)
      </h2>

      {display === null || report === null ? (
        // The 2-landing window: eval runs but has no stats yet. Show NO number — a point
        // estimate here would violate CG-G-S11b, and a placeholder would read as a rate.
        <p className="oa-inf__success-pending" data-testid="success-rate-pending">
          집계 대기 — 평가는 진행 중이나 통계가 아직 없습니다. 성공률 숫자를 표시하지 않습니다.
        </p>
      ) : (
        <>
          <p className="oa-inf__success-headline" data-testid="success-rate">
            <span className="oa-inf__success-point" data-testid="success-rate-point">
              {display.pointEstimatePct}
            </span>
            <span className="oa-inf__success-ci" data-testid="success-rate-ci">
              {display.wilsonText}
            </span>
            <span className="oa-inf__success-n">
              N={display.nTrials} (성공 {display.nSuccess})
            </span>
          </p>

          {display.clopperPearsonText && (
            <p className="oa-inf__success-cp" data-testid="success-rate-cp">
              {display.clopperPearsonText}
            </p>
          )}

          {!display.meaningful && (
            <p className="oa-inf__meaningless" role="status" data-testid="meaningless-badge">
              {display.meaninglessLabel} — 우열 판정 미출력 (N&lt;20)
            </p>
          )}

          <p className="oa-inf__ranking-note" data-testid="ranking-note" data-ranking-allowed={display.rankingAllowed}>
            {display.rankingAllowed ? "체크포인트 우열 비교 가능" : "표본 부족으로 순위/우열 미출력"}
          </p>

          <dl className="oa-inf__success-items">
            <div>
              <dt>기준선</dt>
              <dd data-testid="baseline-kind">{report.baselineKind}</dd>
            </div>
            <div>
              <dt>에피소드 길이 중앙값</dt>
              <dd>{report.episodeLengthMedian}</dd>
            </div>
            <div>
              <dt>충돌 횟수</dt>
              <dd>{report.collisionCount}</dd>
            </div>
            <div>
              <dt>토크 한계 도달</dt>
              <dd>{report.torqueLimitHits}</dd>
            </div>
            <div>
              <dt>안전정지 발동</dt>
              <dd>{report.safetyStopCount}</dd>
            </div>
            <div>
              <dt>추론 지연 p95</dt>
              <dd>{report.inferenceLatencyP95} ms</dd>
            </div>
          </dl>
        </>
      )}
    </section>
  );
}
