// The model behind the two safety stops (CG-G-03a, FR-GUI-063/064). OpenArm has
// no holding brake, so the two stops are physically opposite outcomes and must
// never collapse into one control: a soft stop holds the pose with motor torque,
// a hard E-Stop cuts power and the load falls.
//
// Only one of them is a control here. The soft stop is a command this GUI sends; the
// hard E-Stop is a physical button this GUI can only point at. They are kept in one
// module because the operator meets them side by side and the distinction between
// them is the whole point — separating the files would let one be read without the
// other.

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

// Hard E-Stop: an external power-line cut, described here and never actuated here.
// `13` §2.7 enumerates every network edge this system has and not one of them can open
// a contactor, so the only thing that cuts power is a hand on the power-line button
// (NORM-007, `16` §4 M-2). It carries its own type rather than `StopKindSpec` so no
// caller can hand it a click handler: a control that looks like the others and reaches
// nothing is read as a stop that works, and that misreading happens at the moment the
// operator has the least time to check.
export interface PhysicalStopSpec {
  kind: StopKind;
  label: string;
  // What the stop physically does — the distinction an operator must not confuse.
  effect: string;
  // Where the hand has to go, because no software path substitutes for it.
  actuation: string;
}

export const PHYSICAL_ESTOP: PhysicalStopSpec = {
  kind: "hard",
  label: "하드 E-Stop",
  effect: "전원 차단 — 팔이 낙하한다",
  actuation: "전원라인 물리 버튼 — 소프트웨어 경로 없음",
};

// The standing drop warning shown next to the hard E-Stop at all times
// (FR-GUI-064). It is never behind a toggle or a scroll region: an operator who
// reaches for the hard stop must always see that it drops the load.
export const HARD_ESTOP_DROP_WARNING =
  "전원 차단 시 파지 중인 물체가 낙하합니다";
