// CG-G-02f: on a browser-aux vs backend-MJCF FK disagreement, the backend value is
// forced and a warning raised — the browser never substitutes its own EE number.

import { describe, expect, it } from "vitest";

import { reconcileEndEffector, type EePose } from "./fkReconcile";

const BACKEND: EePose = { x: 0.4, y: 0.1, z: 0.3 };

describe("CG-G-02f EE FK reconciliation", () => {
  it("returns the backend pose and no warning when no aux pose is given", () => {
    const result = reconcileEndEffector(BACKEND, null);
    expect(result.pose).toEqual(BACKEND);
    expect(result.warned).toBe(false);
    expect(result.deltaM).toBe(0);
  });

  it("returns the backend pose and no warning when aux agrees within tolerance", () => {
    const aux: EePose = { x: 0.4009, y: 0.1, z: 0.3 };
    const result = reconcileEndEffector(BACKEND, aux, 0.005);
    expect(result.pose).toEqual(BACKEND);
    expect(result.warned).toBe(false);
  });

  it("forces the backend pose and warns when aux diverges beyond tolerance", () => {
    const aux: EePose = { x: 0.5, y: 0.1, z: 0.3 };
    const result = reconcileEndEffector(BACKEND, aux, 0.005);
    expect(result.pose).toEqual(BACKEND);
    expect(result.warned).toBe(true);
    expect(result.deltaM).toBeCloseTo(0.1);
  });
});
