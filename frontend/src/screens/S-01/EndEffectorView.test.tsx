// The selector renders the backend's tool list and nothing of its own, states the
// eighth-motor consequence beside each choice, shows an unmeasured mass as a fact
// that blocks no control, and refuses — shows no selection — when the stored id is
// not one the backend registered.

import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ToolChoice } from "../../config/endEffectorTools";
import type { EndEffectorConfig } from "../../config/schema";
import { EndEffectorView } from "./EndEffectorView";
import { MASS_UNMEASURED_TEXT, TOOLS_UNREADABLE_TEXT } from "./endEffector";

// Deliberately NOT today's two tools: the control must render whatever the
// registry sends, so the fixture uses ids this repo has never seen.
const REGISTRY: ToolChoice[] = [
  { toolId: "flat_probe", label: "평면 프로브", gripperMotor: false },
  { toolId: "pinch_v9", label: "핀치 v9", gripperMotor: true },
  { toolId: "suction_cup", label: "석션 컵", gripperMotor: false },
];

function fitted(leftToolId: string, rightToolId: string): EndEffectorConfig {
  return {
    left: { toolId: leftToolId, toolMassKg: null },
    right: { toolId: rightToolId, toolMassKg: null },
  };
}

function renderView(overrides: Partial<Parameters<typeof EndEffectorView>[0]> = {}) {
  const props = {
    endEffector: fitted("flat_probe", "flat_probe"),
    tools: REGISTRY,
    toolsNotice: null,
    configNotice: null,
    saveNotice: null,
    onSelectTool: vi.fn(),
    ...overrides,
  };
  return { ...render(<EndEffectorView {...props} />), props };
}

function choice(container: HTMLElement, side: string, toolId: string): HTMLInputElement {
  return container.querySelector<HTMLInputElement>(
    `[data-ee-choice="${side}:${toolId}"] input[type="radio"]`,
  )!;
}

describe("end-effector selector", () => {
  it("renders every tool the backend sent, for both arms", () => {
    const { container } = renderView();

    for (const side of ["left", "right"]) {
      const arm = screen.getByTestId(`ee-arm-${side}`);
      for (const tool of REGISTRY) {
        expect(within(arm).getByText(tool.label)).toBeInTheDocument();
        expect(choice(container, side, tool.toolId)).not.toBeNull();
      }
    }
  });

  it("marks the fitted tool per arm, independently", () => {
    const { container } = renderView({ endEffector: fitted("pinch_v9", "suction_cup") });

    expect(choice(container, "left", "pinch_v9").checked).toBe(true);
    expect(choice(container, "left", "suction_cup").checked).toBe(false);
    expect(choice(container, "right", "suction_cup").checked).toBe(true);
    expect(choice(container, "right", "pinch_v9").checked).toBe(false);
  });

  it("states whether the eighth motor is addressed, beside each choice", () => {
    const { container } = renderView();

    const withGripper = container.querySelector('[data-ee-choice="left:pinch_v9"]')!;
    expect(withGripper.textContent).toContain("여덟 번째 모터");
    expect(withGripper.textContent).toContain("0x08");
    expect(withGripper.textContent).toContain("ERROR-PASSIVE");

    const withoutGripper = container.querySelector('[data-ee-choice="left:flat_probe"]')!;
    expect(withoutGripper.textContent).toContain("여덟 번째 모터");
    expect(withoutGripper.textContent).toContain("부르지 않습니다");
  });

  it("reports the operator's choice with the arm it belongs to", () => {
    const onSelectTool = vi.fn();
    const { container } = renderView({ onSelectTool });

    fireEvent.click(choice(container, "right", "pinch_v9"));

    expect(onSelectTool).toHaveBeenCalledWith("right", "pinch_v9");
  });

  it("shows an unmeasured mass as a fact and blocks no control", () => {
    const { container } = renderView({
      endEffector: {
        left: { toolId: "flat_probe", toolMassKg: null },
        right: { toolId: "flat_probe", toolMassKg: 0.35 },
      },
      onSelectTool: vi.fn(),
    });

    const unmeasured = screen.getByTestId("ee-mass-left");
    expect(unmeasured).toHaveAttribute("data-mass-measured", "false");
    expect(unmeasured.textContent).toContain(MASS_UNMEASURED_TEXT);
    // A fact, not an error: no alert role anywhere on the mass line.
    expect(unmeasured.getAttribute("role")).toBeNull();

    // Every control on the unmeasured arm still works.
    for (const tool of REGISTRY) {
      expect(choice(container, "left", tool.toolId).disabled).toBe(false);
    }
    fireEvent.click(choice(container, "left", "pinch_v9"));
    expect(screen.getByTestId("ee-arm-left")).toBeInTheDocument();

    const measured = screen.getByTestId("ee-mass-right");
    expect(measured).toHaveAttribute("data-mass-measured", "true");
    expect(measured.textContent).toContain("0.35");
  });

  it("shows no selection when the stored id is not one the backend registered", () => {
    const { container } = renderView({ endEffector: fitted("retired_tool", "flat_probe") });

    for (const tool of REGISTRY) {
      expect(choice(container, "left", tool.toolId).checked).toBe(false);
    }
    expect(screen.getByTestId("ee-unknown-left").textContent).toContain("retired_tool");
    // The other arm is unaffected — one unknown id does not blank the rig.
    expect(choice(container, "right", "flat_probe").checked).toBe(true);
    expect(screen.queryByTestId("ee-unknown-right")).toBeNull();
  });

  it("offers no choices at all when the registry could not be read", () => {
    const { container } = renderView({ tools: [], toolsNotice: TOOLS_UNREADABLE_TEXT });

    expect(container.querySelectorAll('input[type="radio"]').length).toBe(0);
    expect(screen.getByTestId("ee-tools-notice")).toHaveTextContent(TOOLS_UNREADABLE_TEXT);
    expect(screen.queryByTestId("ee-arm-left")).toBeNull();
  });

  it("shows no fitted tool when the config could not be read", () => {
    const { container } = renderView({ endEffector: null, configNotice: "설정을 읽지 못했습니다." });

    expect(container.querySelectorAll('input[type="radio"]').length).toBe(0);
    expect(screen.getByTestId("ee-config-notice")).toBeInTheDocument();
  });
});

// The four refusals below were all UNTESTED when this file first landed: each mutation kept the
// suite green. They are grouped because they share one consequence — a tool id that is wrong,
// stale or unreadable decides whether CAN id 0x08 is polled on that arm, and polling a motor
// that is not on the bus walks the controller to ERROR-PASSIVE, degrading the seven joints that
// are present. A selection shown for an id the backend does not register is worse than none.
describe("refusals that decide whether an absent motor gets polled", () => {
  it("shows no selection at all when the stored id is not registered", () => {
    renderView({ endEffector: fitted("retired_tool", REGISTRY[0].toolId) });

    const leftArm = screen.getByTestId("ee-arm-left");
    for (const choice of REGISTRY) {
      const radio = within(leftArm).getByDisplayValue(choice.toolId) as HTMLInputElement;
      expect(radio.checked).toBe(false);
    }
  });

  it("treats an id differing only in case as unregistered", () => {
    // Case-folding the comparison would make "Pinch_V9" select the gripper tool — a silent
    // promotion from "no motor 0x08" to "motor 0x08 is polled".
    renderView({ endEffector: fitted("Pinch_V9", REGISTRY[0].toolId) });

    const leftArm = screen.getByTestId("ee-arm-left");
    const gripperRadio = within(leftArm).getByDisplayValue("pinch_v9") as HTMLInputElement;
    expect(gripperRadio.checked).toBe(false);
  });

  it("shows no fitted tool when the config could not be read", () => {
    renderView({ endEffector: null });

    expect(screen.queryByTestId("ee-arm-left")).toBeNull();
    expect(screen.queryByTestId("ee-arm-right")).toBeNull();
  });

  it("shows no fitted tool when the registry could not be read", () => {
    // Without the registry there is nothing to check a stored id against, so a rendered
    // selection would be an unverified claim about which motors exist.
    renderView({ tools: [], toolsNotice: TOOLS_UNREADABLE_TEXT });

    expect(screen.queryByTestId("ee-arm-left")).toBeNull();
  });
});
