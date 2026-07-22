// CG-G-S04j: the active home profile's name and target pose are shown before
// execution. More than one home definition exists and they are physically
// different poses (§2.10: driver home has J4 = pi/2, the MoveIt all-zero pose sits
// on J4's hard stop), so pressing Home without seeing which pose it drives to is
// unsafe. The profiles and their targets are the backend's; the screen renders
// them and the operator picks.

import { render, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ManualScreen from "./screen";
import { HomePanel } from "./HomePanel";
import { defaultManualSource } from "./manualSource";

describe("CG-G-S04j active home profile name + target pose shown before execution", () => {
  it("offers more than one home profile", () => {
    const base = defaultManualSource();
    expect(base.home.profiles.length).toBeGreaterThan(1);
  });

  it("shows the selected profile's name and rad target pose", () => {
    const base = defaultManualSource();
    const { container } = render(
      <HomePanel
        home={base.home}
        side="right"
        activeProfileId="driver_home"
        onProfileChange={vi.fn()}
        canMove
        onCommand={vi.fn()}
      />,
    );
    const preview = container.querySelector('[data-field="home-preview"]') as HTMLElement;
    expect(within(preview).getByText(/활성 프로파일: driver\/MuJoCo home/)).toBeInTheDocument();
    const target = container.querySelector('[data-field="home-target-pose"]') as HTMLElement;
    expect(target.getAttribute("data-unit")).toBe("rad");
    expect(target.textContent).toMatch(/1\.5708/);
  });

  it("warns that the all-zero MoveIt profile is the J4 hard-stop pose", () => {
    const base = defaultManualSource();
    const { container } = render(
      <HomePanel
        home={base.home}
        side="right"
        activeProfileId="moveit_home"
        onProfileChange={vi.fn()}
        canMove
        onCommand={vi.fn()}
      />,
    );
    expect(within(container as unknown as HTMLElement).getByText(/하드스톱/)).toBeInTheDocument();
  });

  it("renders the home preview in the full screen before execution", () => {
    const { container } = render(<ManualScreen />);
    expect(container.querySelector('[data-field="home-profile-name"]')).not.toBeNull();
    expect(container.querySelector('[data-field="home-target-pose"]')).not.toBeNull();
  });
});
