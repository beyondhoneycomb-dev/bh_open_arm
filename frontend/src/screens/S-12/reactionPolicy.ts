// Reaction-policy projection for the collision/safety screen. The set of
// policies, their default, their stop categories, and which of them drop the
// load are domain facts owned by SAF (12 §2.7 / §2.10, FR-SAF-037); this module
// MIRRORS them so the selector can render the choices and warn on the dropping
// ones. It decides nothing: choosing a policy emits a control-frame intent the
// backend applies. The screen is a window onto SAF, not a second source of
// truth (CG-G-S12d sibling rule).
//
// The default is STOP_HOLD (IEC 60204-1 stop category 2, power retained), never
// a power cut. OpenArm has no holding brake, so a power-cut reaction to a
// collision answers the collision with a drop — that is exactly the failure
// CG-G-S12a and FR-SAF-038 forbid.

export const REACTION_MODES = [
  "STOP_HOLD",
  "STOP_DECEL",
  "GRAVITY_COMP",
  "RETRACT",
  "ADMITTANCE",
  "POWER_OFF",
] as const;
export type ReactionMode = (typeof REACTION_MODES)[number];

// FR-SAF-037: the default reaction is STOP_HOLD (Cat-2, no drop).
export const DEFAULT_REACTION_MODE: ReactionMode = "STOP_HOLD";

// The one reaction that cuts power (stop category 0). With no holding brake this
// is the policy that drops the load — the hard-E-Stop equivalent among reaction
// policies, and never a safe default (§2.10).
export const POWER_CUT_REACTION_MODE: ReactionMode = "POWER_OFF";

export interface ReactionModeSpec {
  mode: ReactionMode;
  label: string;
  // IEC 60204-1 stop category, or null for the compliance/retract policies that
  // are not stops at all (§2.7).
  stopCategory: 0 | 1 | 2 | null;
  // Whether applying this policy drops the load. The one fact an operator must
  // never misread on a brakeless arm.
  dropsLoad: boolean;
  // What the policy physically does, in the operator's terms (§2.7 table).
  effect: string;
}

export const REACTION_MODE_SPECS: Readonly<Record<ReactionMode, ReactionModeSpec>> = {
  STOP_HOLD: {
    mode: "STOP_HOLD",
    label: "STOP_HOLD · 보호 정지 (Cat-2)",
    stopCategory: 2,
    dropsLoad: false,
    effect: "토크로 현재 자세 유지 · 전원·CAN 유지 · 낙하 없음",
  },
  STOP_DECEL: {
    mode: "STOP_DECEL",
    label: "STOP_DECEL · 감속 정지 (Cat-1)",
    stopCategory: 1,
    dropsLoad: true,
    effect: "감속 궤적 실행 후 전원 차단 — 최종 낙하",
  },
  GRAVITY_COMP: {
    mode: "GRAVITY_COMP",
    label: "GRAVITY_COMP · 중력 보상 순응",
    stopCategory: null,
    dropsLoad: false,
    effect: "순수 토크 피드포워드 — 사람이 밀어낼 수 있다 · 낙하 없음",
  },
  RETRACT: {
    mode: "RETRACT",
    label: "RETRACT · 후퇴",
    stopCategory: null,
    dropsLoad: false,
    effect: "잔차 방향의 반대로 후퇴 · 낙하 없음",
  },
  ADMITTANCE: {
    mode: "ADMITTANCE",
    label: "ADMITTANCE · 반발",
    stopCategory: null,
    dropsLoad: false,
    effect: "잔차를 속도 명령으로 변환해 반발 · 낙하 없음",
  },
  POWER_OFF: {
    mode: "POWER_OFF",
    label: "POWER_OFF · 전원 차단 (Cat-0)",
    stopCategory: 0,
    dropsLoad: true,
    effect: "전원 차단 — 브레이크 없음 → 낙하 · 최후 수단",
  },
};

export function reactionSpec(mode: ReactionMode): ReactionModeSpec {
  return REACTION_MODE_SPECS[mode];
}

export function reactionDropsLoad(mode: ReactionMode): boolean {
  return REACTION_MODE_SPECS[mode].dropsLoad;
}

// Whether a policy is the power-cut (hard-E-Stop-equivalent) reaction. The
// default must never be this (CG-G-S12a).
export function isPowerCutReaction(mode: ReactionMode): boolean {
  return mode === POWER_CUT_REACTION_MODE;
}

// The selected reaction to render before any backend value arrives, or when the
// backend has not yet reported one: always the safe default, never a power cut.
export function resolveSelectedReaction(backendMode: ReactionMode | null): ReactionMode {
  return backendMode ?? DEFAULT_REACTION_MODE;
}
