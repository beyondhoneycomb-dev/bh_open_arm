// CG-G-S07d: an episode whose drop rate exceeds the display bands is flagged
// (~2% warn / ~5% overload). These bands are presentation only, not the backend
// quality gate; they turn a backend-supplied count into a colour band.

import { describe, expect, it } from "vitest";

import { DROP_RATE_OVERLOAD, DROP_RATE_WARN, dropRate, flagForCounts, flagForRate } from "./dropRate";

describe("drop-rate display bands (CG-G-S07d)", () => {
  it("uses ~2% warn and ~5% overload", () => {
    expect(DROP_RATE_WARN).toBeCloseTo(0.02);
    expect(DROP_RATE_OVERLOAD).toBeCloseTo(0.05);
  });

  it("an empty episode has rate 0, not a divide-by-zero", () => {
    expect(dropRate(3, 0)).toBe(0);
    expect(flagForCounts(3, 0)).toBe("ok");
  });

  it("classifies below, at, and above each band", () => {
    expect(flagForRate(0.0)).toBe("ok");
    expect(flagForRate(DROP_RATE_WARN)).toBe("ok"); // exactly the ceiling is tolerated
    expect(flagForRate(0.03)).toBe("warn");
    expect(flagForRate(DROP_RATE_OVERLOAD)).toBe("warn");
    expect(flagForRate(0.06)).toBe("overload");
  });

  it("flags a 6/100-frame episode as overload and a 3/100 as warn", () => {
    expect(flagForCounts(6, 100)).toBe("overload");
    expect(flagForCounts(3, 100)).toBe("warn");
    expect(flagForCounts(1, 100)).toBe("ok");
  });
});
