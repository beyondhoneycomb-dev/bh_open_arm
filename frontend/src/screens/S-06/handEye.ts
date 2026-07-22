// Hand-eye 5-method compare view-model (CG-G-S06f, CG-G-S06g).
//
// `06` FR-CAM-026 forbids adopting one hand-eye method. cv2.calibrateHandEye's
// TSAI branch is wrong for eye-to-hand (opencv#20974) and some pose regimes break
// "most" methods (opencv#24871), so the backend solves all five simultaneously
// (`HandEyeResult`) and exposes NO accessor that collapses them to one answer.
// This module preserves that discipline: it shapes the five method rows and the
// pairwise agreement for display and offers no "chosen"/"best"/"adopted"
// selector, so a caller can only render the whole set (CG-G-S06f). Frustum trust
// follows calibration freshness — a stale hand-eye means the frustum is drawn
// from a stale extrinsic — so a stale result renders the frustum stale
// (CG-G-S06g). Every number here (residuals, deviations, staleness) is a backend
// fact; the screen computes no transform.

// The five solvers `06` FR-CAM-026 mandates be computed simultaneously, in the
// canonical presentation order. Mirrors the backend
// `HAND_EYE_METHOD_NAMES`; the contract test asserts the two agree.
export const HAND_EYE_METHOD_NAMES = [
  "TSAI",
  "PARK",
  "HORAUD",
  "ANDREFF",
  "DANIILIDIS",
] as const;
export type HandEyeMethodName = (typeof HAND_EYE_METHOD_NAMES)[number];

export type HandEyeSetup = "eye_in_hand" | "eye_to_hand";

export interface HandEyeMethodRow {
  method: HandEyeMethodName;
  // This method's AX=XB self-consistency residual, from the backend solver.
  residualRotationDeg: number;
  residualTranslationMm: number;
}

export interface HandEyeDeviation {
  methodA: HandEyeMethodName;
  methodB: HandEyeMethodName;
  rotationDeg: number;
  translationMm: number;
}

export interface HandEyeView {
  // The camera slot this calibration belongs to.
  slot: string;
  setup: HandEyeSetup;
  samplePoseCount: number;
  // One row per method, in canonical order (all five present).
  methods: readonly HandEyeMethodRow[];
  // Pairwise deviations across the method set.
  deviations: readonly HandEyeDeviation[];
  // Backend calibration freshness. A stale result taints the frustum (CG-G-S06g).
  stale: boolean;
  // Human label for when the calibration was captured (display only).
  capturedLabel: string;
}

export function maxRotationDeviationDeg(view: HandEyeView): number {
  return view.deviations.reduce((max, d) => Math.max(max, d.rotationDeg), 0);
}

export function maxTranslationDeviationMm(view: HandEyeView): number {
  return view.deviations.reduce((max, d) => Math.max(max, d.translationMm), 0);
}

export function methodNames(view: HandEyeView): HandEyeMethodName[] {
  return view.methods.map((row) => row.method);
}

// Whether the five methods cover the mandated set. A UI that renders fewer than
// five has silently collapsed the result — the exact FR-CAM-026 failure.
export function hasAllMethods(view: HandEyeView): boolean {
  const present = new Set(methodNames(view));
  return HAND_EYE_METHOD_NAMES.every((name) => present.has(name));
}
