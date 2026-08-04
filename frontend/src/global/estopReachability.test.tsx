// CG-G-03b: the stop surface must be reachable across every screen x mode x
// {observer, controller}. This renders the always-on GlobalSafetyBar for each of the 208
// matrix cells and asserts two things of every one: the STOP_HOLD control is present —
// NORM-006 fixed FR-GUI-065's subject to STOP_HOLD, not to a power cut — and no clickable
// hard E-Stop exists anywhere, because this rig has no software path to a contactor and a
// button reaching none would be read as a stop that works (NORM-007).

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

  it("renders the STOP_HOLD control in every cell", () => {
    const unreachable: string[] = [];
    for (const cell of estopMatrix()) {
      const { queryByRole, unmount } = render(<GlobalSafetyBar {...propsFor(cell)} />);
      if (!queryByRole("button", { name: /소프트 스톱/ })) {
        unreachable.push(`${cell.screen}|${cell.mode}|${cell.role}`);
      }
      unmount();
    }
    expect(unreachable).toEqual([]);
  });

  it("enables it wherever the client holds control", () => {
    const gated: string[] = [];
    for (const cell of estopMatrix().filter((c) => c.role === "controller")) {
      const { getByRole, unmount } = render(<GlobalSafetyBar {...propsFor(cell)} />);
      if ((getByRole("button", { name: /소프트 스톱/ }) as HTMLButtonElement).disabled) {
        gated.push(`${cell.screen}|${cell.mode}|${cell.role}`);
      }
      unmount();
    }
    expect(gated).toEqual([]);
  });

  // Rendered is not reachable. FR-GUI-065 asks for a stop an observer can press, and
  // NORM-006 fixed its subject to STOP_HOLD — but StopControls gates the soft stop on
  // control authority, so an observer has nothing to press now that the hard E-Stop is a
  // panel. This pins that gap rather than hiding it behind a presence check: opening the
  // soft stop to observers turns this red, which is the point. Until someone does, the
  // matrix above certifies reachability of a control half the cells cannot use.
  it("has NO pressable stop for an observer — the open gap, pinned", () => {
    const pressable: string[] = [];
    for (const cell of estopMatrix().filter((c) => c.role !== "controller")) {
      const { getByRole, unmount } = render(<GlobalSafetyBar {...propsFor(cell)} />);
      if (!(getByRole("button", { name: /소프트 스톱/ }) as HTMLButtonElement).disabled) {
        pressable.push(`${cell.screen}|${cell.mode}|${cell.role}`);
      }
      unmount();
    }
    expect(pressable).toEqual([]);
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
