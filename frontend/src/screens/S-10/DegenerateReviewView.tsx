// The degenerate-channel review (WP-4A-03, FR-TRN-067/068, CG-G-S10 ⑤). For every
// located finding the screen offers ALL THREE choices — EXCLUDE / MANUAL_STATS /
// PROCEED — taken from the one contract set (`presentChoices`) so an option is never
// silently dropped, and records the operator's pick. It owns no detection or resolution
// logic: the findings and their statistics/amplification are the backend's, and the
// start gate (startGate.ts) — not this view — decides that an undecided finding blocks
// training. The view surfaces the choice; the gate enforces it.

import { useState } from "react";

import { presentChoices, undecidedFindings } from "./startGate";
import type { DegenerateChoice, DegenerateDecision, DegenerateFinding } from "./types";

export interface DegenerateReviewViewProps {
  findings: readonly DegenerateFinding[];
  decisions: readonly DegenerateDecision[];
  onResolve: (finding: DegenerateFinding, choice: DegenerateChoice, rationale: string) => void;
}

const CHOICE_LABEL: Readonly<Record<DegenerateChoice, string>> = {
  EXCLUDE: "채널 제외",
  MANUAL_STATS: "수동 통계 대체",
  PROCEED: "무시하고 진행",
};

function decisionFor(
  finding: DegenerateFinding,
  decisions: readonly DegenerateDecision[],
): DegenerateDecision | undefined {
  return decisions.find(
    (decision) =>
      decision.finding.channelName === finding.channelName &&
      decision.finding.normMode === finding.normMode,
  );
}

export function DegenerateReviewView({ findings, decisions, onResolve }: DegenerateReviewViewProps) {
  const [rationales, setRationales] = useState<Record<string, string>>({});
  const pending = undecidedFindings(findings, decisions);

  function keyOf(finding: DegenerateFinding): string {
    return `${finding.channelName}::${finding.normMode}`;
  }

  return (
    <section
      className="oa-trn__panel"
      aria-labelledby="oa-trn-degenerate-title"
      data-testid="degenerate-review"
      data-pending={pending.length}
    >
      <h2 id="oa-trn-degenerate-title" className="oa-trn__section-title">
        퇴화 채널 검토 (3택 필수)
      </h2>

      {findings.length === 0 ? (
        <p data-testid="degenerate-empty">검출된 퇴화 채널이 없습니다.</p>
      ) : (
        <ul className="oa-trn__degenerate-list">
          {findings.map((finding) => {
            const decided = decisionFor(finding, decisions);
            const key = keyOf(finding);
            return (
              <li
                key={key}
                className="oa-trn__degenerate-item"
                data-testid={`degenerate-${finding.channelName}`}
                data-decided={decided !== undefined}
              >
                <p className="oa-trn__degenerate-loc">
                  {finding.channelName} · {finding.joint}
                  {finding.component ?? ""} · {finding.normMode}
                </p>
                <p className="oa-trn__muted">
                  통계 {finding.statistic.toExponential(2)} &lt; 임계 {finding.threshold.toExponential(2)} ·
                  증폭 추정 ×{finding.amplificationEstimate.toExponential(1)}
                </p>

                <input
                  type="text"
                  className="oa-trn__rationale"
                  placeholder="근거 (계보에 기록됨)"
                  value={rationales[key] ?? ""}
                  data-testid={`degenerate-rationale-${finding.channelName}`}
                  onChange={(event) =>
                    setRationales((prev) => ({ ...prev, [key]: event.target.value }))
                  }
                />

                <div className="oa-trn__choices" role="group" aria-label="퇴화 채널 결정">
                  {presentChoices().map((choice) => (
                    <button
                      key={choice}
                      type="button"
                      className="oa-trn__choice"
                      data-testid={`degenerate-choice-${finding.channelName}-${choice}`}
                      aria-pressed={decided?.choice === choice}
                      onClick={() => onResolve(finding, choice, rationales[key] ?? "")}
                    >
                      {CHOICE_LABEL[choice]}
                    </button>
                  ))}
                </div>

                {decided !== undefined && (
                  <p className="oa-trn__decided" data-testid={`degenerate-decided-${finding.channelName}`}>
                    결정: {CHOICE_LABEL[decided.choice]}
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
