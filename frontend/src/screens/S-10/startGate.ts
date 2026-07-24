// The training-start gate (CG-G-S10 ⑤ / FR-TRN-068, and CG-G-S10e VRAM). There must be
// ZERO UI paths that begin training while a degenerate channel is undecided, the
// dataset preflight has not PASSED, the chosen policy is blocked, or VRAM does not fit.
// The gate mirrors the backend `clear_for_training` (WP-4A-03) so the screen refuses
// exactly what the backend would refuse — it composes those decisions, it does not
// invent them. The screen routes EVERY start action — the start button and a checkpoint
// resume alike — through one `canStartTraining`-guarded emitter, so the create-job intent
// is unreachable while any blocker stands.

import { DEGENERATE_CHOICES } from "./types";
import type {
  DegenerateChoice,
  DegenerateDecision,
  DegenerateFinding,
  PolicyOption,
  PreflightReport,
  VramPreflight,
} from "./types";

// The three choices that must be offered for every finding (backend `present_choices`).
// Re-exported from the one contract set so the review UI cannot silently drop an option.
export function presentChoices(): readonly DegenerateChoice[] {
  return DEGENERATE_CHOICES;
}

// The findings that have no matching decision (backend `undecided_findings`). A finding
// is decided when some decision carries an equal finding; equality is by located value
// (channel + norm mode + statistic), never by array position.
export function undecidedFindings(
  findings: readonly DegenerateFinding[],
  decisions: readonly DegenerateDecision[],
): DegenerateFinding[] {
  const decided = decisions.map((decision) => decision.finding);
  return findings.filter((finding) => !decided.some((other) => sameFinding(finding, other)));
}

function sameFinding(a: DegenerateFinding, b: DegenerateFinding): boolean {
  return (
    a.channelName === b.channelName &&
    a.normMode === b.normMode &&
    a.statistic === b.statistic &&
    a.threshold === b.threshold
  );
}

// The gate inputs, one object so the screen and the tests pass the same shape.
export interface StartGateInput {
  policy: PolicyOption | null;
  preflight: PreflightReport;
  findings: readonly DegenerateFinding[];
  decisions: readonly DegenerateDecision[];
  vram: VramPreflight;
}

// Every human-readable reason the start is blocked, in the order an operator resolves
// them. Empty means the gate is clear. The screen shows these and disables the start
// control whenever the list is non-empty; there is no other start path.
export function startBlockReasons(input: StartGateInput): string[] {
  const reasons: string[] = [];

  if (input.policy === null) {
    reasons.push("정책이 선택되지 않았습니다");
  } else if (input.policy.blocked) {
    reasons.push(
      `선택한 정책이 차단됨: ${input.policy.blockReason?.human ?? "구조적으로 사용 불가"}`,
    );
  }

  if (input.preflight.verdict !== "PASS") {
    reasons.push(
      `데이터셋 프리플라이트가 BLOCK 상태입니다 (미해결 결함 ${input.preflight.findings.length}건)`,
    );
  }

  const pending = undecidedFindings(input.findings, input.decisions);
  if (pending.length > 0) {
    const located = pending.map((finding) => `${finding.channelName} (${finding.normMode})`);
    reasons.push(
      `퇴화 채널 ${pending.length}건에 EXCLUDE/MANUAL_STATS/PROCEED 결정이 없습니다: ` +
        `${located.join(", ")} (FR-TRN-068)`,
    );
  }

  if (!input.vram.fits) {
    reasons.push(
      `VRAM 부족: ${input.vram.requiredGb}GB 필요 / ${input.vram.availableGb}GB 가용 ` +
        `(출처: ${input.vram.source})`,
    );
  }

  return reasons;
}

// Whether training may start: the gate is clear only when no reason stands.
export function canStartTraining(input: StartGateInput): boolean {
  return startBlockReasons(input).length === 0;
}
