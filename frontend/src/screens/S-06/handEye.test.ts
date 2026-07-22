import { describe, expect, it } from "vitest";

import {
  HAND_EYE_METHOD_NAMES,
  hasAllMethods,
  maxRotationDeviationDeg,
  maxTranslationDeviationMm,
  methodNames,
  type HandEyeView,
} from "./handEye";

function fullView(overrides: Partial<HandEyeView> = {}): HandEyeView {
  return {
    slot: "right_wrist",
    setup: "eye_in_hand",
    samplePoseCount: 12,
    methods: HAND_EYE_METHOD_NAMES.map((method) => ({
      method,
      residualRotationDeg: 0.3,
      residualTranslationMm: 1.2,
    })),
    deviations: [
      { methodA: "TSAI", methodB: "PARK", rotationDeg: 0.6, translationMm: 2.4 },
      { methodA: "PARK", methodB: "DANIILIDIS", rotationDeg: 0.1, translationMm: 0.5 },
    ],
    stale: false,
    capturedLabel: "recent",
    ...overrides,
  };
}

describe("hand-eye five-method invariant (CG-G-S06f)", () => {
  it("fixes the five method names and their canonical order", () => {
    expect(HAND_EYE_METHOD_NAMES).toEqual(["TSAI", "PARK", "HORAUD", "ANDREFF", "DANIILIDIS"]);
  });

  it("reports the full method set present", () => {
    const view = fullView();
    expect(methodNames(view)).toEqual(HAND_EYE_METHOD_NAMES);
    expect(hasAllMethods(view)).toBe(true);
  });

  it("detects a collapsed result missing methods", () => {
    const collapsed = fullView({ methods: [{ method: "TSAI", residualRotationDeg: 0.3, residualTranslationMm: 1 }] });
    expect(hasAllMethods(collapsed)).toBe(false);
  });

  it("surfaces the largest pairwise deviation for the agreement read", () => {
    const view = fullView();
    expect(maxRotationDeviationDeg(view)).toBeCloseTo(0.6);
    expect(maxTranslationDeviationMm(view)).toBeCloseTo(2.4);
  });
});
