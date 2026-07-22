import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { StopControls } from "./StopControls";
import { HARD_ESTOP_DROP_WARNING } from "./stopControls";

describe("CG-G-03a the two stops are distinct controls with a standing drop warning", () => {
  it("renders two separate stop buttons with distinct kinds and classes", () => {
    render(<StopControls onSoftStop={() => {}} onHardEStop={() => {}} hasControl />);
    const soft = screen.getByRole("button", { name: /소프트 스톱/ });
    const hard = screen.getByRole("button", { name: /하드 E-Stop/ });
    expect(soft).toHaveAttribute("data-stop-kind", "soft");
    expect(hard).toHaveAttribute("data-stop-kind", "hard");
    // Visually distinct: different modifier classes, so they never render alike.
    expect(soft.className).toContain("oa-stop--soft");
    expect(hard.className).toContain("oa-stop--hard");
    expect(soft.className).not.toBe(hard.className);
  });

  it("routes each stop to its own handler — the two paths never merge", () => {
    const onSoftStop = vi.fn();
    const onHardEStop = vi.fn();
    render(<StopControls onSoftStop={onSoftStop} onHardEStop={onHardEStop} hasControl />);

    fireEvent.click(screen.getByRole("button", { name: /소프트 스톱/ }));
    expect(onSoftStop).toHaveBeenCalledTimes(1);
    expect(onHardEStop).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /하드 E-Stop/ }));
    expect(onHardEStop).toHaveBeenCalledTimes(1);
    expect(onSoftStop).toHaveBeenCalledTimes(1);
  });

  it("shows the standing drop warning next to the hard E-Stop", () => {
    render(<StopControls onSoftStop={() => {}} onHardEStop={() => {}} hasControl />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(HARD_ESTOP_DROP_WARNING);
    // The warning sits inside the hard-stop group, adjacent to the hard button.
    const hardGroup = alert.closest(".oa-stop-hard");
    expect(hardGroup).not.toBeNull();
    expect(within(hardGroup as HTMLElement).getByRole("button")).toHaveAttribute(
      "data-stop-kind",
      "hard",
    );
  });

  it("keeps the hard E-Stop enabled even without control; only the soft stop is gated", () => {
    render(<StopControls onSoftStop={() => {}} onHardEStop={() => {}} hasControl={false} />);
    expect(screen.getByRole("button", { name: /하드 E-Stop/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /소프트 스톱/ })).toBeDisabled();
  });
});
