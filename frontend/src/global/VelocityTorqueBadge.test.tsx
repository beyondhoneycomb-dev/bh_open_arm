import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { VelocityTorqueBadge } from "./VelocityTorqueBadge";
import { VELOCITY_TORQUE_OFF_WARNING } from "./flags";

describe("VelocityTorqueBadge (CG-G-03c render)", () => {
  it("shows the warning message and warning tone when off", () => {
    render(<VelocityTorqueBadge state={{ enabled: false }} onToggle={() => {}} />);
    const badge = screen.getByRole("status");
    expect(badge.className).toContain("oa-badge--warning");
    expect(badge).toHaveTextContent(VELOCITY_TORQUE_OFF_WARNING);
  });

  it("shows no warning and a nominal tone when on", () => {
    render(<VelocityTorqueBadge state={{ enabled: true }} onToggle={() => {}} />);
    const badge = screen.getByRole("status");
    expect(badge.className).toContain("oa-badge--nominal");
    expect(badge).not.toHaveTextContent(VELOCITY_TORQUE_OFF_WARNING);
  });

  it("exposes exactly one coupled switch (no per-arm control)", () => {
    render(<VelocityTorqueBadge state={{ enabled: false }} onToggle={() => {}} />);
    const switches = screen.getAllByRole("checkbox");
    expect(switches.length).toBe(1);
    expect(switches[0]).toHaveAccessibleName(/커플드/);
  });

  it("toggles through the single coupled value", () => {
    const onToggle = vi.fn();
    render(<VelocityTorqueBadge state={{ enabled: false }} onToggle={onToggle} />);
    fireEvent.click(screen.getByRole("checkbox"));
    expect(onToggle).toHaveBeenCalledWith(true);
  });
});
