import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadgeBar, type StatusBadgeBarProps } from "./StatusBadgeBar";

function props(overrides: Partial<StatusBadgeBarProps> = {}): StatusBadgeBarProps {
  return {
    robot: { connected: true, mode: "RECORD", profileName: "stiff", controlHolder: "session-1" },
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
    onToggleVelocityTorque: () => {},
    ...overrides,
  };
}

describe("StatusBadgeBar (FR-GUI-060/061/072/073)", () => {
  it("renders the required always-on badges", () => {
    const { container } = render(<StatusBadgeBar {...props()} />);
    expect(container.querySelector('[data-badge="connection"]')).not.toBeNull();
    expect(container.querySelector('[data-badge="mode"]')).toHaveTextContent("RECORD");
    expect(container.querySelector('[data-badge="profile"]')).toHaveTextContent("stiff");
    expect(container.querySelector('[data-badge="control-holder"]')).toHaveTextContent("session-1");
    expect(container.querySelector('[data-flag="use_velocity_and_torque"]')).not.toBeNull();
    expect(container.querySelector('[data-flag="push_to_hub"]')).not.toBeNull();
  });

  it("marks the profile badge as a warning when no profile is loaded", () => {
    const { container } = render(
      <StatusBadgeBar {...props({ robot: { connected: false, mode: "IDLE", profileName: null, controlHolder: null } })} />,
    );
    const profile = container.querySelector('[data-badge="profile"]');
    expect(profile?.className).toContain("oa-badge--warning");
    expect(screen.getByText("미로드")).toBeInTheDocument();
  });
});
