// The model behind the two safety stops (CG-G-03a, FR-GUI-063/064). OpenArm has
// no holding brake, so the two stops are physically opposite outcomes and must
// never collapse into one control: a soft stop holds the pose with motor torque,
// a hard E-Stop cuts power and the load falls. Each stop is a distinct kind with
// its own handler; there is deliberately no merged "stop(kind)" dispatcher, so a
// caller cannot accidentally wire one button to both outcomes.

export const STOP_KINDS = ["soft", "hard"] as const;
export type StopKind = (typeof STOP_KINDS)[number];

export interface StopKindSpec {
  kind: StopKind;
  // Short control label shown on the button.
  label: string;
  // What the stop physically does — the distinction an operator must not confuse.
  effect: string;
}

// Soft stop: command becomes STOP_HOLD, torque holds the current pose. This is
// not a loop halt (I-3) — the CAN command stream keeps flowing.
export const SOFT_STOP: StopKindSpec = {
  kind: "soft",
  label: "소프트 스톱",
  effect: "모터 토크로 현재 자세 유지 (STOP_HOLD)",
};

// Hard E-Stop: external power-line cut. With no holding brake the arm drops.
export const HARD_ESTOP: StopKindSpec = {
  kind: "hard",
  label: "하드 E-Stop",
  effect: "전원 차단 — 팔이 낙하한다",
};

// The standing drop warning shown next to the hard E-Stop at all times
// (FR-GUI-064). It is never behind a toggle or a scroll region: an operator who
// reaches for the hard stop must always see that it drops the load.
export const HARD_ESTOP_DROP_WARNING =
  "전원 차단 시 파지 중인 물체가 낙하합니다";
