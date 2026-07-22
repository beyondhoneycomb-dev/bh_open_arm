// CG-G-02i: publish rate defaults to 30 Hz, caps at 60 Hz, and rejects (does not
// clamp) an over-cap or malformed request.

import { describe, expect, it } from "vitest";

import { resolvePublishRate } from "./publishRate";

describe("CG-G-02i publish-rate resolution", () => {
  it("defaults to 30 Hz when unset", () => {
    const result = resolvePublishRate();
    expect(result).toEqual({ ok: true, hz: 30 });
  });

  it("accepts a rate at or below the 60 Hz cap", () => {
    expect(resolvePublishRate(45)).toEqual({ ok: true, hz: 45 });
    expect(resolvePublishRate(60)).toEqual({ ok: true, hz: 60 });
  });

  it("rejects a rate above the cap rather than clamping it", () => {
    const result = resolvePublishRate(61);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.reason).toContain("60");
      expect(result.requested).toBe(61);
    }
  });

  it("rejects non-positive and non-finite requests", () => {
    expect(resolvePublishRate(0).ok).toBe(false);
    expect(resolvePublishRate(-5).ok).toBe(false);
    expect(resolvePublishRate(Number.NaN).ok).toBe(false);
    expect(resolvePublishRate(Number.POSITIVE_INFINITY).ok).toBe(false);
  });
});
