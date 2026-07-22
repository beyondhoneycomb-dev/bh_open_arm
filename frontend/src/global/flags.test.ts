import { describe, expect, it } from "vitest";

import {
  PUSH_TO_HUB_UPLOAD_WARNING,
  VELOCITY_TORQUE_OFF_WARNING,
  pushToHubRequiresConfirm,
  setVelocityTorqueCoupled,
  velocityTorqueIsWarning,
  type PushToHubState,
  type VelocityTorqueState,
} from "./flags";

describe("CG-G-03c use_velocity_and_torque is a coupled switch with an off-warning", () => {
  it("warns when off and not when on", () => {
    expect(velocityTorqueIsWarning({ enabled: false })).toBe(true);
    expect(velocityTorqueIsWarning({ enabled: true })).toBe(false);
  });

  it("carries the off warning text", () => {
    expect(VELOCITY_TORQUE_OFF_WARNING).toMatch(/기록되지 않습니다/);
  });

  it("mutates through a single coupled value that applies to both arms", () => {
    const on: VelocityTorqueState = setVelocityTorqueCoupled(true);
    const off: VelocityTorqueState = setVelocityTorqueCoupled(false);
    expect(on).toEqual({ enabled: true });
    expect(off).toEqual({ enabled: false });
    // The state shape has exactly one field: there is no per-arm value to diverge.
    expect(Object.keys(on)).toEqual(["enabled"]);
  });
});

describe("CG-G-03d push_to_hub forces confirmation when on", () => {
  const on: PushToHubState = { enabled: true, private: false, tags: [] };
  const off: PushToHubState = { enabled: false, private: true, tags: [] };

  it("requires confirmation only when push_to_hub is on", () => {
    expect(pushToHubRequiresConfirm(on)).toBe(true);
    expect(pushToHubRequiresConfirm(off)).toBe(false);
  });

  it("carries the upload warning text", () => {
    expect(PUSH_TO_HUB_UPLOAD_WARNING).toMatch(/Hugging Face Hub/);
  });
});
