// The success-rate formatter (CG-G-S11b/c, the 4C increment). This is the SOLE reader of
// a report's `pointEstimate`: nowhere else in the S-11 tree reads that field, and here the
// point estimate is NEVER produced without its Wilson 95% CI beside it. A bare point
// estimate is a readable lie — N=5 at 60% and N=200 at 60% look identical — so the display
// object below always carries the CI, and the static check (staticChecks.test.ts) proves
// `pointEstimate` appears in no other shipped file. When N < N_MIN_MEANINGFUL the display
// flags the report statistically-meaningless and forbids ranking (CG-G-S11c). A null report
// returns null so the caller renders NO number during the 4B->4C landing window (the
// 2-landing note) — never a placeholder that would read as a real rate.

import type { ConfidenceInterval, SuccessRateReport } from "./types";
import { N_MIN_MEANINGFUL, STATISTICALLY_MEANINGLESS_LABEL } from "./types";

// A proportion in [0, 1] as a one-decimal percentage, e.g. 0.65 -> "65.0%".
function formatPercent(proportion: number): string {
  return `${(proportion * 100).toFixed(1)}%`;
}

// A CI as "[lower, upper]" in percentage points.
function formatInterval(interval: ConfidenceInterval): string {
  return `[${formatPercent(interval.lower)}, ${formatPercent(interval.upper)}]`;
}

// The render-ready success-rate view. Every field that carries the rate also carries the
// CI: `summary` and `withCi` are inseparable point+CI text, and `pointEstimatePct` is only
// ever shown by the panel alongside `wilsonText` in the same element. `meaningful` gates
// ranking; `meaninglessLabel` is the flag shown when N is below the floor.
export interface SuccessRateDisplay {
  nTrials: number;
  nSuccess: number;
  pointEstimatePct: string;
  wilsonText: string;
  wilsonLowerPct: string;
  wilsonUpperPct: string;
  clopperPearsonText: string | null;
  withCi: string;
  summary: string;
  meaningful: boolean;
  meaninglessLabel: string | null;
  rankingAllowed: boolean;
}

// Build the display from a report, or null during the 2-landing window (report absent).
// The point estimate is read exactly once, on the line that also reads the Wilson CI, so
// the two cannot be separated by a later edit.
export function describeSuccessRate(
  report: SuccessRateReport | null,
): SuccessRateDisplay | null {
  if (report === null) {
    return null;
  }
  const wilson = report.ciWilson95;
  const pointEstimatePct = formatPercent(report.pointEstimate);
  const wilsonText = `Wilson 95% CI ${formatInterval(wilson)}`;
  const withCi = `${pointEstimatePct} (${wilsonText})`;
  const clopperPearsonText =
    report.ciClopperPearson95 === null
      ? null
      : `Clopper-Pearson 95% CI ${formatInterval(report.ciClopperPearson95)}`;
  const meaningful = report.statisticallyMeaningful;
  const summary = meaningful
    ? withCi
    : `${withCi} — ${STATISTICALLY_MEANINGLESS_LABEL} (N<${N_MIN_MEANINGFUL})`;
  return {
    nTrials: report.nTrials,
    nSuccess: report.nSuccess,
    pointEstimatePct,
    wilsonText,
    wilsonLowerPct: formatPercent(wilson.lower),
    wilsonUpperPct: formatPercent(wilson.upper),
    clopperPearsonText,
    withCi,
    summary,
    meaningful,
    meaninglessLabel: meaningful ? null : STATISTICALLY_MEANINGLESS_LABEL,
    rankingAllowed: meaningful,
  };
}
