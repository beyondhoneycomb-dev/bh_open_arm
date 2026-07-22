// CG-G-S05f: while a VR session is active the GUI manual-control affordance is
// DISABLED, so there is no UI state in which two sources issue commands at once.

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CommandSourceBar } from "./CommandSourceBar";
import { defaultTeleopSource, type TeleopSource } from "./teleopSource";

function withSession(active: boolean, overrides: Partial<TeleopSource["session"]> = {}): TeleopSource {
  const base = defaultTeleopSource();
  return { ...base, session: { ...base.session, active, ...overrides } };
}

describe("CommandSourceBar (CG-G-S05f)", () => {
  it("disables the manual-control affordance while a VR session is active", () => {
    render(<CommandSourceBar source={withSession(true)} onManualControl={vi.fn()} />);
    const manual = screen.getByRole("button", { name: "GUI 수동 조작" });
    expect(manual).toBeDisabled();
    expect(manual).toHaveAttribute("data-disabled", "true");
  });

  it("enables manual control only when no VR session holds the source", () => {
    render(<CommandSourceBar source={withSession(false)} onManualControl={vi.fn()} />);
    expect(screen.getByRole("button", { name: "GUI 수동 조작" })).toBeEnabled();
  });

  it("names exactly one active command source", () => {
    const { rerender } = render(<CommandSourceBar source={withSession(false)} onManualControl={vi.fn()} />);
    expect(screen.getByRole("status")).toHaveAttribute("data-source", "gui_manual_available");

    rerender(<CommandSourceBar source={withSession(true, { transport: "webxr" })} onManualControl={vi.fn()} />);
    expect(screen.getByRole("status")).toHaveAttribute("data-source", "vr_webxr");
  });
});
