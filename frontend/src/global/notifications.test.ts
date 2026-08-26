import { describe, expect, it } from "vitest";

import { Severity } from "./contracts/errorCodes";
import {
  acknowledge,
  badgeIsHeld,
  heldCount,
  type Notification,
} from "./notifications";

function make(
  severity: number,
  blocking: boolean,
  acked: boolean,
  id = "n1",
): Notification {
  return {
    id,
    code: "OA-CAN-001",
    severity: severity as Notification["severity"],
    source: "OA-CAN",
    timestamp: 1000,
    detail: "test",
    blocking,
    acked,
  };
}

describe("CG-G-03g the badge is held by what stopped, not by a severity number", () => {
  it("does not hold for an alert that stopped nothing, at any severity", () => {
    // The point of the change: a fault can be loud and still not require a click. If
    // ERROR alone held the badge, an operator would learn to clear it without reading.
    expect(badgeIsHeld([make(Severity.ERROR, false, false)])).toBe(false);
    expect(badgeIsHeld([make(Severity.STALE, false, false)])).toBe(false);
    expect(badgeIsHeld([make(Severity.WARN, false, false)])).toBe(false);
  });

  it("holds for anything that stopped something, at any severity", () => {
    // And the converse: severity does not get a veto. A WARN that latched the arm is
    // still an arm the operator has to release.
    expect(badgeIsHeld([make(Severity.WARN, true, false)])).toBe(true);
    expect(badgeIsHeld([make(Severity.ERROR, true, false)])).toBe(true);
    expect(heldCount([make(Severity.ERROR, true, false)])).toBe(1);
  });

  it("clears only on acknowledgement, and does not mutate the input", () => {
    const before = [make(Severity.ERROR, true, false, "e1")];
    expect(badgeIsHeld(before)).toBe(true);
    const after = acknowledge(before, "e1");
    expect(badgeIsHeld(after)).toBe(false);
    expect(before[0].acked).toBe(false);
  });

  it("keeps holding while any blocking alert is still unacknowledged", () => {
    const list = [
      make(Severity.ERROR, true, false, "e1"),
      make(Severity.ERROR, true, false, "e2"),
    ];
    const partial = acknowledge(list, "e1");
    expect(badgeIsHeld(partial)).toBe(true);
    expect(heldCount(partial)).toBe(1);
  });
});
