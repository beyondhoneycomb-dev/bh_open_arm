import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { StopControls } from "./StopControls";
import { HARD_ESTOP_DROP_WARNING, PHYSICAL_ESTOP } from "./stopControls";

describe("CG-G-03a the two stops are distinct, and only one of them is a control", () => {
  it("renders the soft stop as a button and the hard E-Stop as guidance, with distinct classes", () => {
    render(<StopControls onSoftStop={() => {}} hasControl />);
    const soft = screen.getByRole("button", { name: /소프트 스톱/ });
    expect(soft).toHaveAttribute("data-stop-kind", "soft");
    expect(soft.className).toContain("oa-stop--soft");

    const hard = screen.getByText(PHYSICAL_ESTOP.label).closest(".oa-stop--hard");
    expect(hard).not.toBeNull();
    expect(hard).toHaveAttribute("data-stop-kind", "hard");
    expect((hard as HTMLElement).className).not.toBe(soft.className);
  });

  it("offers no clickable hard E-Stop — this rig has no software power boundary", () => {
    render(<StopControls onSoftStop={() => {}} hasControl />);
    // The single button on this surface is the soft stop. A hard-stop button would be a
    // control wired to nothing, which reads as a stop that works (NORM-007).
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(1);
    expect(buttons[0]).toHaveAttribute("data-stop-kind", "soft");
  });

  it("names where the physical button is, since no software path substitutes for it", () => {
    render(<StopControls onSoftStop={() => {}} hasControl />);
    expect(screen.getByText(PHYSICAL_ESTOP.actuation)).toBeInTheDocument();
  });

  it("routes the soft stop to its own handler", () => {
    const onSoftStop = vi.fn();
    render(<StopControls onSoftStop={onSoftStop} hasControl />);
    fireEvent.click(screen.getByRole("button", { name: /소프트 스톱/ }));
    expect(onSoftStop).toHaveBeenCalledTimes(1);
  });

  it("keeps the standing drop warning beside the hard E-Stop panel", () => {
    render(<StopControls onSoftStop={() => {}} hasControl />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(HARD_ESTOP_DROP_WARNING);
    // Losing the button must not lose the hazard: the warning still sits in the hard group
    // next to the panel that describes it (FR-GUI-064).
    const hardGroup = alert.closest(".oa-stop-hard");
    expect(hardGroup).not.toBeNull();
    expect(
      within(hardGroup as HTMLElement).getByText(PHYSICAL_ESTOP.label),
    ).toBeInTheDocument();
  });

  it("gates the soft stop on control authority", () => {
    render(<StopControls onSoftStop={() => {}} hasControl={false} />);
    expect(screen.getByRole("button", { name: /소프트 스톱/ })).toBeDisabled();
  });
});
