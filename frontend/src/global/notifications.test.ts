import { describe, expect, it } from "vitest";

import { Severity } from "./contracts/errorCodes";
import {
  acknowledge,
  badgeIsHeld,
  heldCount,
  type Notification,
} from "./notifications";

function make(severity: number, acked: boolean, id = "n1"): Notification {
  return {
    id,
    code: "OA-CAN-001",
    severity: severity as Notification["severity"],
    source: "OA-CAN",
    timestamp: 1000,
    detail: "test",
    acked,
  };
}

describe("CG-G-03g ERROR+ alerts hold the badge until acknowledged", () => {
  it("does not hold for OK/WARN", () => {
    expect(badgeIsHeld([make(Severity.OK, false)])).toBe(false);
    expect(badgeIsHeld([make(Severity.WARN, false)])).toBe(false);
  });

  it("holds for an unacknowledged ERROR", () => {
    expect(badgeIsHeld([make(Severity.ERROR, false)])).toBe(true);
    expect(heldCount([make(Severity.ERROR, false)])).toBe(1);
  });

  it("holds for an unacknowledged STALE (above ERROR on the axis)", () => {
    expect(badgeIsHeld([make(Severity.STALE, false)])).toBe(true);
  });

  it("clears the hold only after the ERROR alert is acknowledged", () => {
    const before = [make(Severity.ERROR, false, "e1")];
    expect(badgeIsHeld(before)).toBe(true);
    const after = acknowledge(before, "e1");
    expect(badgeIsHeld(after)).toBe(false);
    // Acknowledging returns a new list and does not mutate the input.
    expect(before[0].acked).toBe(false);
  });

  it("keeps holding while any ERROR+ alert is still unacknowledged", () => {
    const list = [make(Severity.ERROR, false, "e1"), make(Severity.ERROR, false, "e2")];
    const partial = acknowledge(list, "e1");
    expect(badgeIsHeld(partial)).toBe(true);
    expect(heldCount(partial)).toBe(1);
  });
});
