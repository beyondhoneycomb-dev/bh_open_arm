// S-09 is a facade onto the SIM domain (09): it renders backend simulation
// state and sends user intent, and it must not become a second source of truth.
// This module is the browser-side projection of the SIM domain's FROZEN contracts
// — the gain-parity precondition (FR-SIM-028b), the dry-run six-check identity
// (FR-SIM-030), the backend-Robot abstraction (FR-SIM-097), and the standing rule
// that the MuJoCo/MJCF asset is NOT a hardware-spec cross-check basis (FR-SIM-007).
// It carries those contracts through as enums, labels and gate predicates; it does
// NOT re-derive the domain's own clamp math, thresholds or reaction policy. Every
// numeric violation detail rendered by the screen originates in a backend report.

// FR-SIM-097: the simulation runs on ONE LeRobot `Robot` ABC, with the physics
// backend selected at runtime. MuJoCo is the stage-1 canon (CPU, default); Isaac
// is the stage-2 option (GPU). These are backend identities the screen renders,
// not a second adapter layer.
export type SimBackend = "mujoco" | "isaac";
export const DEFAULT_SIM_BACKEND: SimBackend = "mujoco";

export interface SimBackendInfo {
  readonly id: SimBackend;
  readonly label: string;
  // The two-stage boundary (NFR-SIM-008): stage 1 = MuJoCo canon, stage 2 = Isaac.
  readonly stage: 1 | 2;
}

export const SIM_BACKENDS: Readonly<Record<SimBackend, SimBackendInfo>> = {
  mujoco: { id: "mujoco", label: "MuJoCo (1단계 정본 · CPU)", stage: 1 },
  isaac: { id: "isaac", label: "Isaac (2단계 선택 · GPU)", stage: 2 },
};

// The control target the operator's commands are pointed at. FR-SIM-097 / row 205:
// swapping sim <-> real swaps the backend `Robot` OBJECT only. It is NOT a
// connect()/disconnect() — a browser-driven reconnect would re-run the backend
// Robot's set_zero_position and destroy zeroing (I-2). This enum and swapTarget()
// below carry the swap with zero reconnect semantics; the static scan proves it.
export type ControlTarget = "sim" | "real";

export const CONTROL_TARGET_LABELS: Readonly<Record<ControlTarget, string>> = {
  sim: "시뮬 (Robot=BiOpenArmMujoco)",
  real: "실기 (Robot=BiOpenArmFollower)",
};

// Toggle the active control target. A pure object swap: it selects which Robot the
// backend drives and touches no transport. There is deliberately no reconnect,
// disconnect or connect step here — that is the whole point of the frozen contract.
export function swapTarget(current: ControlTarget): ControlTarget {
  return current === "sim" ? "real" : "sim";
}

// FR-SIM-028b: the real arm's PD gain profile is the axis of sim<->real parity.
// `stiff` (230-series, openarm_cell_higher_pd.yaml) is the v2-unique profile the
// v2 MJCF is modelled with; `compliant` (70-series) is the v1v2 common default.
// The profile IDENTITY is backend state the screen renders; the series numbers are
// the profiles' names, NOT hardware specs and NOT a computed threshold.
export type GainProfile = "stiff" | "compliant";

export interface GainProfileInfo {
  readonly id: GainProfile;
  // The PD-gain-profile name, series annotation included. This labels a control
  // gain profile, not a hardware specification.
  readonly label: string;
}

export const GAIN_PROFILES: Readonly<Record<GainProfile, GainProfileInfo>> = {
  stiff: { id: "stiff", label: "stiff (230 계열)" },
  compliant: { id: "compliant", label: "compliant (70 계열)" },
};

// FR-SIM-028b / D-4: digital twin and dry-run REQUIRE the real arm on `stiff`,
// because the MJCF is modelled stiff and any other profile splits the sim/real
// static and transient response, contaminating the residual by the gain gap. This
// is the frozen precondition the facade carries, not a rule the screen invents.
export const TWIN_DRYRUN_REQUIRED_GAIN_PROFILE: GainProfile = "stiff";

// Whether twin / dry-run may start under the given active gain profile. Starting
// on `compliant` is REFUSED (CG-G-S09b) — the backend enforces it too; the screen
// gates the UI so the operator cannot even attempt the parity-broken run.
export function twinDryRunAllowed(activeProfile: GainProfile): boolean {
  return activeProfile === TWIN_DRYRUN_REQUIRED_GAIN_PROFILE;
}

export const GAIN_PARITY_REFUSAL_REASON =
  "sim-real 게인 패리티 깨짐: 트윈·드라이런은 실기 stiff(230 계열) 게인을 강제한다. " +
  "현재 게인 프로파일에서는 거부된다 (FR-SIM-028b).";

// FR-SIM-030: the dry-run checks AT LEAST these six items, in this frozen order.
// The identity of the six is the contract the facade carries; the pass/fail verdict
// and every violation number come from the backend MuJoCo dry-run (FR-SIM-100).
export type DryRunCheckId =
  | "position"
  | "velocity"
  | "torque"
  | "cellCollision"
  | "selfCollision"
  | "lifter";

export interface DryRunCheckMeta {
  readonly id: DryRunCheckId;
  readonly label: string;
}

// Frozen order and labels of the six checks (FR-SIM-030 ①..⑥).
export const DRY_RUN_CHECKS: readonly DryRunCheckMeta[] = [
  { id: "position", label: "관절 위치 한계" },
  { id: "velocity", label: "관절 속도 한계" },
  { id: "torque", label: "액추에이터 토크 한계" },
  { id: "cellCollision", label: "셀 충돌 (벽·천장·레일·테이블)" },
  { id: "selfCollision", label: "자가 충돌 (로봇 geom)" },
  { id: "lifter", label: "리프터 스트로크 (0–0.3 m)" },
];

export const DRY_RUN_CHECK_COUNT = DRY_RUN_CHECKS.length;

export type DryRunCheckStatus = "pass" | "fail" | "not_run";

// A single violation as the backend dry-run reports it (FR-SIM-033): which joint,
// the simulation time it occurred at, and the amount over the limit. The screen
// renders these; it computes none of them.
export interface DryRunViolation {
  readonly joint: string;
  readonly simTimeS: number;
  readonly overshoot: string;
}

export interface DryRunCheckResult {
  readonly id: DryRunCheckId;
  readonly status: DryRunCheckStatus;
  readonly violation?: DryRunViolation;
}

// A dry-run report from the backend: exactly one result per frozen check id, or
// null before any dry-run has run.
export interface DryRunReport {
  readonly checks: readonly DryRunCheckResult[];
}

// Whether every one of the six checks passed. Real-send is hard-gated on this
// (FR-SIM-033, CG-G-S09d): a missing or non-`pass` result never counts as passed.
export function allChecksPassed(report: DryRunReport | null): boolean {
  if (!report) {
    return false;
  }
  return DRY_RUN_CHECKS.every((meta) => {
    const result = report.checks.find((check) => check.id === meta.id);
    return result?.status === "pass";
  });
}

// Line the six frozen checks up against a report so the view renders every item,
// even the ones the backend omitted (rendered as `not_run` rather than dropped).
export function orderedCheckResults(report: DryRunReport | null): DryRunCheckResult[] {
  return DRY_RUN_CHECKS.map((meta) => {
    const result = report?.checks.find((check) => check.id === meta.id);
    return result ?? { id: meta.id, status: "not_run" };
  });
}

// FR-SIM-007 / §2.6: the v2 MJCF is internally inconsistent — joint7 is declared
// `motor_DM3507` while its actuator is `position_DM4310`, and the real J7 is DM4310
// (four primary sources agree). This is a SIMULATION-ASSET bug. The screen may
// surface it, but only ever as an asset fact — never as a hardware-spec basis. The
// basis type below has exactly one inhabitant, so no MJCF fact can be authored as
// a hardware-spec claim (CG-G-S09a, static half).
export type FactBasis = "sim-asset-only";

export interface MjcfAssetFact {
  readonly id: string;
  readonly label: string;
  readonly detail: string;
  readonly basis: FactBasis;
}

export const MJCF_ASSET_FACTS: readonly MjcfAssetFact[] = [
  {
    id: "j7-motor-class",
    label: "J7 모터 클래스 불일치",
    detail:
      "MJCF는 joint7을 motor_DM3507로, 액추에이터를 position_DM4310으로 선언한다 " +
      "(파일 내부 모순). 실기 J7 = DM4310 확정. 이는 시뮬 자산의 오기다.",
    basis: "sim-asset-only",
  },
];

// The standing disclaimer that must be visible whenever an MJCF fact is shown: the
// MuJoCo model is not a cross-check source for hardware specification (FR-SIM-007).
export const MJCF_NOT_HARDWARE_SPEC_DISCLAIMER =
  "MuJoCo/MJCF 모델은 하드웨어 사양의 교차확인 근거가 아니다. " +
  "아래는 시뮬레이션 자산 사실일 뿐이며, 실기 사양을 확인해 주지 않는다 (FR-SIM-007).";

// Per-fact tag rendered on every MJCF fact card, so no asset value can read as a
// hardware spec even in isolation.
export const SIM_ASSET_TAG = "시뮬 자산 (하드웨어 사양 아님)";

// Structural guard for CG-G-S09a: no MJCF fact is ever a hardware-spec basis.
export function noMjcfFactIsHardwareSpec(): boolean {
  return MJCF_ASSET_FACTS.every((fact) => fact.basis === "sim-asset-only");
}

// CG-G-S09e: the sim/real ghost overlay must be visually UNMISTAKABLE. Each layer
// carries a distinct colour, opacity and outline so the two never blur together.
export interface GhostLayerStyle {
  readonly target: ControlTarget;
  readonly label: string;
  readonly colorToken: string;
  readonly opacity: number;
  readonly outline: "solid" | "dashed";
}

export const GHOST_LAYER_STYLES: Readonly<Record<ControlTarget, GhostLayerStyle>> = {
  real: {
    target: "real",
    label: "실기 (REAL)",
    colorToken: "#f5a623",
    opacity: 1,
    outline: "solid",
  },
  sim: {
    target: "sim",
    label: "시뮬 고스트 (SIM)",
    colorToken: "#37c9d6",
    opacity: 0.45,
    outline: "dashed",
  },
};

// Whether the two ghost layers differ on every visual dimension. If any dimension
// coincided the overlay would be ambiguous, which CG-G-S09e forbids.
export function ghostLayersAreDistinct(): boolean {
  const sim = GHOST_LAYER_STYLES.sim;
  const real = GHOST_LAYER_STYLES.real;
  return (
    sim.colorToken !== real.colorToken &&
    sim.opacity !== real.opacity &&
    sim.outline !== real.outline &&
    sim.label !== real.label
  );
}
