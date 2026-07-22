import { describe, expect, it } from "vitest";

import { MODES, externalCanClientModes, modeById } from "./modes";

describe("mode authority catalog (FR-GUI-080)", () => {
  it("names exactly the eight modes", () => {
    expect(MODES.map((mode) => mode.id)).toEqual([
      "IDLE",
      "MANUAL",
      "TELEOP_VR",
      "TELEOP_KER",
      "RECORD",
      "INFERENCE",
      "SIM",
      "MOTOR_SETUP",
    ]);
  });

  it("gives IDLE no send_action holder and no real-bus drive", () => {
    const idle = modeById("IDLE");
    expect(idle.holder).toBe("none");
    expect(idle.drivesRealBus).toBe(false);
  });

  it("marks MOTOR_SETUP as the only mode allowing an external CAN client (CG-G-04e)", () => {
    expect(externalCanClientModes()).toEqual(["MOTOR_SETUP"]);
    for (const mode of MODES) {
      if (mode.id !== "MOTOR_SETUP") {
        expect(mode.allowsExternalCanClient).toBe(false);
      }
    }
  });

  it("keeps SIM off the real bus but not an external-CLI mode", () => {
    const sim = modeById("SIM");
    expect(sim.drivesRealBus).toBe(false);
    expect(sim.allowsExternalCanClient).toBe(false);
  });

  it("throws on an unknown mode id", () => {
    // @ts-expect-error unknown id is rejected at the type level too
    expect(() => modeById("NOPE")).toThrow(/unknown mode id/);
  });
});
