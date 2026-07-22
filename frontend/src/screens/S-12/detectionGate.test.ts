// CG-G-S12b (logic half): while PG-FRIC-001 is not passed the gate forbids any
// enable path and demands a standing banner (FR-SAF-030). Torque observation off
// is a second, independent blocker (FR-SAF-072). The render half is in
// screen.test.tsx / staticChecks.test.ts.

import { describe, expect, it } from "vitest";

import {
  FRICTION_UNIDENTIFIED_BANNER,
  TORQUE_OBSERVATION_OFF_BANNER,
  evaluateDetectionGate,
} from "./detectionGate";

describe("CG-G-S12b: detection gate", () => {
  it("blocks enablement and shows the friction banner when PG-FRIC-001 is not passed", () => {
    const gate = evaluateDetectionGate({
      frictionGate: "not_passed",
      torqueObservationEnabled: true,
    });
    expect(gate.enableAllowed).toBe(false);
    expect(gate.forcedStatus).toBe("DISABLED");
    expect(gate.bannerText).toBe(FRICTION_UNIDENTIFIED_BANNER);
    expect(gate.blockers[0]).toBe("friction_unidentified");
  });

  it("blocks enablement when torque observation is off (FR-SAF-072)", () => {
    const gate = evaluateDetectionGate({
      frictionGate: "passed",
      torqueObservationEnabled: false,
    });
    expect(gate.enableAllowed).toBe(false);
    expect(gate.bannerText).toBe(TORQUE_OBSERVATION_OFF_BANNER);
    expect(gate.blockers).toContain("torque_observation_off");
  });

  it("reports friction first when both preconditions are unmet", () => {
    const gate = evaluateDetectionGate({
      frictionGate: "not_passed",
      torqueObservationEnabled: false,
    });
    expect(gate.blockers).toEqual(["friction_unidentified", "torque_observation_off"]);
    expect(gate.bannerText).toBe(FRICTION_UNIDENTIFIED_BANNER);
  });

  it("permits enablement only when both preconditions are met", () => {
    const gate = evaluateDetectionGate({
      frictionGate: "passed",
      torqueObservationEnabled: true,
    });
    expect(gate.enableAllowed).toBe(true);
    expect(gate.forcedStatus).toBeNull();
    expect(gate.bannerText).toBeNull();
    expect(gate.blockers).toEqual([]);
  });
});
