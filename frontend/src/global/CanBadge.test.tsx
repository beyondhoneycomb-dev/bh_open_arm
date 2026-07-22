import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CanBadge } from "./CanBadge";
import type { CanInterfaceStatus } from "./canStatus";

function status(overrides: Partial<CanInterfaceStatus> = {}): CanInterfaceStatus {
  return {
    iface: "can0",
    flockHeld: true,
    boundSocketCount: 1,
    intruderPids: [],
    linkState: "ERROR-ACTIVE",
    canFdConfigured: true,
    ...overrides,
  };
}

describe("CanBadge (CG-G-03e render)", () => {
  it("shows intruder PIDs and marks control blocked when a second socket appears", () => {
    render(<CanBadge status={status({ boundSocketCount: 2, intruderPids: [4321, 8765] })} />);
    const badge = screen.getByRole("status");
    expect(badge).toHaveAttribute("data-can-state", "INTRUDED");
    expect(badge).toHaveAttribute("data-control-blocked", "true");
    expect(screen.getByTestId("can-intruder-pids")).toHaveTextContent("4321");
    expect(screen.getByTestId("can-intruder-pids")).toHaveTextContent("8765");
  });

  it("shows no intruder line and does not block control on a clean bus", () => {
    render(<CanBadge status={status()} />);
    expect(screen.getByRole("status")).toHaveAttribute("data-control-blocked", "false");
    expect(screen.queryByTestId("can-intruder-pids")).toBeNull();
  });
});
