// CG-G-03b: the stop surface must be reachable across every screen x mode x
// {observer, controller}. This renders the always-on GlobalSafetyBar for each of the 208
// matrix cells and asserts two things of every one: the STOP_HOLD control is present and
// pressable — NORM-006 fixed FR-GUI-065's subject to STOP_HOLD, not to a power cut — and
// no clickable hard E-Stop exists anywhere, because this rig has no software path to a
// contactor and a button reaching none would be read as a stop that works (NORM-007).
//
// This file proves the component's own behaviour given props. That the shell actually
// mounts it on every route is a separate claim, proven in app/safetyMount.test.tsx.

import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { GlobalSafetyBar, type GlobalSafetyBarProps } from "./GlobalSafetyBar";
import { ESTOP_MATRIX_SIZE, estopMatrix, type SafetyContext } from "./modes";
import { PHYSICAL_ESTOP } from "./stopControls";

function propsFor(context: SafetyContext): GlobalSafetyBarProps {
  return {
    context,
    robot: { connected: true, mode: context.mode, profileName: "stiff", controlHolder: "session-1" },
    canInterfaces: [
      {
        iface: "can0",
        flockHeld: true,
        boundSocketCount: 1,
        intruderPids: [],
        linkState: "ERROR-ACTIVE",
        canFdConfigured: true,
      },
    ],
    velocityTorque: { enabled: true },
    pushToHub: { enabled: false, private: true, tags: [] },
    notifications: [],
    dummyMode: false,
    onSoftStop: () => {},
    onToggleVelocityTorque: () => {},
  };
}

describe("CG-G-03b stop surface reachable across the whole screen x mode x role matrix", () => {
  it("enumerates all 208 cells", () => {
    expect(estopMatrix().length).toBe(ESTOP_MATRIX_SIZE);
  });

  // Rendered is not reachable — a present but disabled button stops nothing. FR-GUI-063
  // makes STOP_HOLD a pressable control and FR-GUI-065 requires it reachable regardless of
  // who holds control, which CTR-WS@v2 supports by carrying `stop_hold` as a frame with
  // control_frame: false. So the requirement is one property over the whole matrix, not two
  // per role: in every cell the control exists AND is pressable. Both failure modes are
  // collected separately so a red run names which one occurred.
  it("renders a pressable STOP_HOLD control in every cell, whoever holds control", () => {
    const missing: string[] = [];
    const disabled: string[] = [];
    for (const cell of estopMatrix()) {
      const { queryByRole, unmount } = render(<GlobalSafetyBar {...propsFor(cell)} />);
      const label = `${cell.screen}|${cell.mode}|${cell.role}`;
      const stop = queryByRole("button", { name: /소프트 스톱/ }) as HTMLButtonElement | null;
      if (!stop) {
        missing.push(label);
      } else if (stop.disabled) {
        disabled.push(label);
      }
      unmount();
    }
    expect({ missing, disabled }).toEqual({ missing: [], disabled: [] });
  });

  it("renders the physical-E-Stop guidance in every cell, and never as a button", () => {
    const offenders: string[] = [];
    for (const cell of estopMatrix()) {
      const { queryByText, queryByRole, unmount } = render(<GlobalSafetyBar {...propsFor(cell)} />);
      const label = `${cell.screen}|${cell.mode}|${cell.role}`;
      if (!queryByText(PHYSICAL_ESTOP.actuation)) {
        offenders.push(`${label}: guidance missing`);
      }
      if (queryByRole("button", { name: new RegExp(PHYSICAL_ESTOP.label) })) {
        offenders.push(`${label}: hard E-Stop rendered as a button`);
      }
      unmount();
    }
    expect(offenders).toEqual([]);
  });
});
