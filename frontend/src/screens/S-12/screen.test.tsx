// Integration checks for the whole /safety screen against the offline fixtures.
// CG-G-S12b render half is here: with PG-FRIC-001 not passed (the fixture's real
// state) there is zero enable-detection path and a standing banner; only when the
// backend reports the gate met does an enable control appear.

import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import SafetyScreen from "./screen";
import { FRICTION_UNIDENTIFIED_BANNER } from "./detectionGate";
import { defaultSafetyScreenSource, noopIntents, type SafetyScreenSource } from "./source";

function gateMetSource(): SafetyScreenSource {
  return {
    ...defaultSafetyScreenSource(),
    frictionGate: "passed",
    torqueObservationEnabled: true,
    detectionStatus: "ARMED",
  };
}

describe("S-12 /safety screen", () => {
  it("renders offline with no backend and shows every panel", () => {
    const { container } = render(<SafetyScreen />);
    expect(container.querySelector(".oa-safety")).not.toBeNull();
    expect(container.querySelector("#oa-safety-detection-title")).not.toBeNull();
    expect(container.querySelector("#oa-safety-reaction-title")).not.toBeNull();
    expect(container.querySelector("#oa-safety-residual-title")).not.toBeNull();
    expect(container.querySelector("#oa-safety-wall-title")).not.toBeNull();
    expect(container.querySelector("#oa-safety-contact-title")).not.toBeNull();
    expect(container.querySelector("#oa-safety-events-title")).not.toBeNull();
  });

  it("CG-G-S12b: no enable-detection path and a standing banner while PG-FRIC-001 is not passed", () => {
    const { container, getByText } = render(<SafetyScreen />);
    // The fixture's real state is friction not passed → zero enable controls.
    expect(container.querySelectorAll('[data-action="enable-detection"]')).toHaveLength(0);
    const banner = container.querySelector('[data-standing-banner="detection"]');
    expect(banner).not.toBeNull();
    expect(getByText(FRICTION_UNIDENTIFIED_BANNER)).toBeInTheDocument();
  });

  it("CG-G-S12b: an enable control appears only once the backend reports the gate met", () => {
    const { container } = render(<SafetyScreen source={gateMetSource()} />);
    expect(container.querySelectorAll('[data-action="enable-detection"]')).toHaveLength(1);
    expect(container.querySelector('[data-standing-banner="detection"]')).toBeNull();
  });

  it("CG-G-S12a: the reaction selector defaults to STOP_HOLD in the composed screen", () => {
    const { container } = render(<SafetyScreen />);
    const stopHold = container.querySelector<HTMLInputElement>(
      '[data-reaction-option="STOP_HOLD"] input',
    );
    const powerOff = container.querySelector<HTMLInputElement>(
      '[data-reaction-option="POWER_OFF"] input',
    );
    expect(stopHold?.checked).toBe(true);
    expect(powerOff?.checked).toBe(false);
  });

  it("emits the enable intent when the gate permits it", () => {
    const intents = { ...noopIntents(), onEnableDetection: vi.fn() };
    const { container } = render(<SafetyScreen source={gateMetSource()} intents={intents} />);
    container.querySelector<HTMLButtonElement>('[data-action="enable-detection"]')!.click();
    expect(intents.onEnableDetection).toHaveBeenCalledTimes(1);
  });
});
