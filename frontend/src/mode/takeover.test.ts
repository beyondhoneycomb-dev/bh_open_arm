import { describe, expect, it } from "vitest";

import { planForceTakeover, type ForceTakeoverRequest } from "./takeover";

function request(overrides: Partial<ForceTakeoverRequest>): ForceTakeoverRequest {
  return {
    user: "op-1",
    role: "admin",
    reason: "이전 세션 교착 — 복구 필요",
    firstConfirm: true,
    secondConfirm: true,
    outgoingSession: "sess-old",
    incomingSession: "sess-new",
    ...overrides,
  };
}

describe("force-takeover (FR-GUI-085, CG-G-04f)", () => {
  it("produces an audit record, a generation bump and a torque-retained plan", () => {
    const result = planForceTakeover(request({}), 7, 123);
    expect(result.ok).toBe(true);
    if (!result.ok) {
      return;
    }
    expect(result.plan.nextLeaseGeneration).toBe(8);
    expect(result.plan.torqueRetainedAsStopHold).toBe(true);
    expect(result.plan.audit).toEqual({
      t: 123,
      user: "op-1",
      role: "admin",
      action: "force_takeover",
      target: "sess-old",
      before: "holder=sess-old",
      after: "holder=sess-new",
      reason: "이전 세션 교착 — 복구 필요",
    });
  });

  it("requires a reason", () => {
    const result = planForceTakeover(request({ reason: "   " }), 7, 123);
    expect(result).toEqual({ ok: false, errors: ["reason_required"] });
  });

  it("requires both confirmations", () => {
    expect(planForceTakeover(request({ secondConfirm: false }), 7, 123)).toEqual({
      ok: false,
      errors: ["double_confirm_required"],
    });
    expect(planForceTakeover(request({ firstConfirm: false }), 7, 123)).toEqual({
      ok: false,
      errors: ["double_confirm_required"],
    });
  });

  it("requires an admin role (FR-OPS-078)", () => {
    const result = planForceTakeover(request({ role: "operator" }), 7, 123);
    expect(result).toEqual({ ok: false, errors: ["admin_role_required"] });
  });

  it("reports every missing requirement at once", () => {
    const result = planForceTakeover(
      request({ role: "observer", reason: "", firstConfirm: false, secondConfirm: false }),
      7,
      123,
    );
    expect(result).toEqual({
      ok: false,
      errors: ["admin_role_required", "reason_required", "double_confirm_required"],
    });
  });
});
