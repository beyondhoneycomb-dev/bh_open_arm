// CG-G-03b: the emergency stop must be reachable across every screen x mode x
// {observer, controller}. This renders the always-on GlobalSafetyBar for each of
// the 208 matrix cells and asserts the hard E-Stop is present and enabled — in
// particular for observers, who cannot command control but must still cut power.

import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { GlobalSafetyBar, type GlobalSafetyBarProps } from "./GlobalSafetyBar";
import { ESTOP_MATRIX_SIZE, estopMatrix, type SafetyContext } from "./modes";

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
    onHardEStop: () => {},
    onToggleVelocityTorque: () => {},
  };
}

describe("CG-G-03b E-Stop reachable across the whole screen x mode x role matrix", () => {
  it("enumerates all 208 cells", () => {
    expect(estopMatrix().length).toBe(ESTOP_MATRIX_SIZE);
  });

  it("renders an enabled hard E-Stop in every cell", () => {
    const unreachable: string[] = [];
    for (const cell of estopMatrix()) {
      const { getByRole, unmount } = render(<GlobalSafetyBar {...propsFor(cell)} />);
      const hard = getByRole("button", { name: /하드 E-Stop/ });
      if (!hard || (hard as HTMLButtonElement).disabled) {
        unreachable.push(`${cell.screen}|${cell.mode}|${cell.role}`);
      }
      unmount();
    }
    expect(unreachable).toEqual([]);
  });
});
