// CG-G-S02c (unit): the forced re-zero flow (unavoidable hardware relink) advances
// all four steps in order, none skippable, and completes only with an audit reason
// — yielding the audit entry the backend persists.

import { describe, expect, it } from "vitest";

import {
  acknowledgeNewZeroWarning,
  addConfirmation,
  confirmRestPose,
  currentRezeroStep,
  DOUBLE_CONFIRM_COUNT,
  INITIAL_REZERO_STATE,
  rezeroAuditEntry,
  rezeroComplete,
  REZERO_STEP_IDS,
  recordAudit,
  type RezeroState,
} from "./rezeroFlow";

function runToComplete(reason: string): RezeroState {
  let state = INITIAL_REZERO_STATE;
  state = confirmRestPose(state);
  state = acknowledgeNewZeroWarning(state);
  state = addConfirmation(state);
  state = addConfirmation(state);
  state = recordAudit(state, reason);
  return state;
}

describe("CG-G-S02c re-zero four-step gate", () => {
  it("starts on the rest-pose confirm step", () => {
    expect(currentRezeroStep(INITIAL_REZERO_STATE)).toBe("rest_pose_confirm");
    expect(REZERO_STEP_IDS).toEqual([
      "rest_pose_confirm",
      "new_zero_warning",
      "double_confirm",
      "audit_log",
    ]);
  });

  it("refuses to skip a step out of order", () => {
    expect(acknowledgeNewZeroWarning(INITIAL_REZERO_STATE)).toBe(INITIAL_REZERO_STATE);
    expect(addConfirmation(INITIAL_REZERO_STATE)).toBe(INITIAL_REZERO_STATE);
    expect(recordAudit(INITIAL_REZERO_STATE, "x")).toBe(INITIAL_REZERO_STATE);
  });

  it("needs two independent confirmations for the double-confirm step", () => {
    let state = confirmRestPose(INITIAL_REZERO_STATE);
    state = acknowledgeNewZeroWarning(state);
    state = addConfirmation(state);
    expect(currentRezeroStep(state)).toBe("double_confirm");
    expect(state.confirmCount).toBe(1);
    state = addConfirmation(state);
    expect(state.confirmCount).toBe(DOUBLE_CONFIRM_COUNT);
    expect(currentRezeroStep(state)).toBe("audit_log");
  });

  it("does not complete without an audit reason", () => {
    let state = confirmRestPose(INITIAL_REZERO_STATE);
    state = acknowledgeNewZeroWarning(state);
    state = addConfirmation(state);
    state = addConfirmation(state);
    state = recordAudit(state, "   ");
    expect(rezeroComplete(state)).toBe(false);
    expect(rezeroAuditEntry(state, "left", 100)).toBeNull();
  });

  it("completes after all four steps and yields the audit entry", () => {
    const state = runToComplete("CAN 어댑터 교체");
    expect(rezeroComplete(state)).toBe(true);
    expect(rezeroAuditEntry(state, "left", 4242)).toEqual({
      action: "hardware_swap_rezero",
      reason: "CAN 어댑터 교체",
      side: "left",
      monoMs: 4242,
    });
  });
});
