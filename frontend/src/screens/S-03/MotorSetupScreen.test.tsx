// Render proofs for the S-03 acceptance checks that need the DOM: the always-on
// active-profile display and the unloaded control block (CG-G-S03e), the seven ERR
// codes each shown with code + recovery hint (CG-G-S03g), the temperatures coming
// straight from the injected state frame (CG-G-S03b), the gripper's per-unit torque
// with no force-unit label (CG-G-S03a), and the refused save when a gain leaves the
// MIT range (CG-G-S03c).

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { MotorSetupScreen } from "./MotorSetupScreen";
import type { MotorSetupSink } from "./motorDomain";
import { ERROR_REGISTRY, loadedSource } from "./testSupport/fixtures";

function sink(overrides: Partial<MotorSetupSink> = {}): MotorSetupSink {
  return {
    loadProfile: vi.fn(),
    saveProfile: vi.fn(),
    captureGripperEndpoint: vi.fn(),
    ...overrides,
  };
}

describe("CG-G-S03e: active profile name shown always + control blocked while unloaded", () => {
  it("shows the active profile name when one is loaded and does not block control", () => {
    render(<MotorSetupScreen source={loadedSource()} sink={sink()} />);
    expect(screen.getByText(/활성 프로파일: lerobot_follower/)).toBeInTheDocument();
    expect(document.querySelector("[data-control-blocked]")).toBeNull();
  });

  it("still shows the active-profile field and blocks control when none is loaded", () => {
    render(
      <MotorSetupScreen source={loadedSource({ activeProfileName: null })} sink={sink()} />,
    );
    expect(document.querySelector("[data-active-profile]")).not.toBeNull();
    expect(screen.getByText(/none loaded/)).toBeInTheDocument();
    expect(document.querySelector("[data-control-blocked]")).not.toBeNull();
  });
});

describe("CG-G-S03g: the seven ERR codes render with code + recovery hint", () => {
  it("renders one row per fault code, each carrying the registry recovery hint", () => {
    render(<MotorSetupScreen source={loadedSource()} sink={sink()} />);
    for (const code of Object.keys(ERROR_REGISTRY)) {
      const cell = document.querySelector(`[data-err-code="${code}"]`);
      expect(cell, code).not.toBeNull();
      const hint = document.querySelector(`[data-recovery-hint="${code}"]`);
      expect(hint?.textContent).toBe(ERROR_REGISTRY[code].recoveryHint);
    }
  });
});

describe("CG-G-S03b: temperatures come from the injected state frame", () => {
  it("renders the per-motor temperatures the frame carried", () => {
    render(<MotorSetupScreen source={loadedSource()} sink={sink()} />);
    const row = document.querySelector('[data-motor-state="J5"]');
    expect(row).not.toBeNull();
    expect(within(row as HTMLElement).getByText("52 °C")).toBeInTheDocument();
    expect(within(row as HTMLElement).getByText("49 °C")).toBeInTheDocument();
  });
});

describe("CG-G-S03a: gripper force is per-unit torque with no N/Nm label", () => {
  it("shows the torque_pu value and its per-unit label", () => {
    render(<MotorSetupScreen source={loadedSource()} sink={sink()} />);
    expect(screen.getByText(/torque_pu \(per-unit\)/)).toBeInTheDocument();
    const value = document.querySelector("[data-gripper-torque-pu]");
    expect(value?.textContent).toBe("0.222");
  });

  it("shows the reachable speed (clamped to vMax), not the raw configured 50", () => {
    render(<MotorSetupScreen source={loadedSource()} sink={sink()} />);
    const reachable = document.querySelector("[data-gripper-speed-reachable]");
    expect(reachable?.textContent).toBe("30");
    expect(document.querySelector("[data-gripper-speed-capped]")).not.toBeNull();
  });
});

describe("CG-G-S03c: an out-of-range gain refuses the save and never calls the sink", () => {
  it("disables save and lists the reason when a kp is edited past 500", async () => {
    const user = userEvent.setup();
    const saveProfile = vi.fn();
    render(<MotorSetupScreen source={loadedSource()} sink={sink({ saveProfile })} />);

    const kpInput = screen.getByLabelText("J1 kp");
    await user.clear(kpInput);
    await user.type(kpInput, "600");

    expect(document.querySelector('[data-refusal="profile-save"]')).not.toBeNull();
    const saveButton = screen.getByRole("button", { name: /프로파일 저장/ });
    expect(saveButton).toBeDisabled();

    await user.click(saveButton);
    expect(saveProfile).not.toHaveBeenCalled();
  });

  it("saves a valid edit through the sink", async () => {
    const user = userEvent.setup();
    const saveProfile = vi.fn();
    render(<MotorSetupScreen source={loadedSource()} sink={sink({ saveProfile })} />);

    const kpInput = screen.getByLabelText("J1 kp");
    await user.clear(kpInput);
    await user.type(kpInput, "200");

    const saveButton = screen.getByRole("button", { name: /프로파일 저장/ });
    expect(saveButton).toBeEnabled();
    await user.click(saveButton);
    expect(saveProfile).toHaveBeenCalledTimes(1);
  });
});
