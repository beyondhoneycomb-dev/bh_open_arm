// CG-G-S05b: following cannot start while alignment is incomplete. The screen renders
// the backend `converged` verdict and offers no follow-start path that bypasses it;
// the only recovery affordance (re-engage) routes a hold back through ALIGNING, never
// straight into FOLLOWING (05 §4.2 #1/#2/#3, FR-TEL-082).

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AlignmentStateMachineView } from "./AlignmentStateMachineView";
import { defaultTeleopSource, type TeleopSource } from "./teleopSource";

function withAlignment(overrides: Partial<TeleopSource["alignment"]>): TeleopSource {
  const base = defaultTeleopSource();
  return { ...base, alignment: { ...base.alignment, ...overrides } };
}

describe("AlignmentStateMachineView (CG-G-S05b)", () => {
  it("blocks follow readiness while alignment has not converged", () => {
    render(
      <AlignmentStateMachineView
        source={withAlignment({ currentState: "S3", converged: false })}
        onReEngage={vi.fn()}
      />,
    );
    const readiness = screen.getByText(/추종 불가 — 정렬 미완/);
    expect(readiness).toBeInTheDocument();
    expect(readiness).toHaveAttribute("data-blocked", "true");
  });

  it("reports follow-ready once alignment converges", () => {
    render(
      <AlignmentStateMachineView
        source={withAlignment({ currentState: "S3", converged: true })}
        onReEngage={vi.fn()}
      />,
    );
    const readiness = screen.getByText(/추종 준비 완료/);
    expect(readiness).toHaveAttribute("data-blocked", "false");
  });

  it("only enables re-engage from a hold state and requests a re-engage intent", () => {
    const onReEngage = vi.fn();
    const { rerender } = render(
      <AlignmentStateMachineView
        source={withAlignment({ currentState: "S4", converged: true })}
        onReEngage={onReEngage}
      />,
    );
    // FOLLOWING is not a hold: re-engage is disabled.
    expect(screen.getByRole("button", { name: /재-engage/ })).toBeDisabled();

    rerender(
      <AlignmentStateMachineView
        source={withAlignment({ currentState: "S5", converged: false })}
        onReEngage={onReEngage}
      />,
    );
    const reengage = screen.getByRole("button", { name: /재-engage/ });
    expect(reengage).toBeEnabled();
    fireEvent.click(reengage);
    expect(onReEngage).toHaveBeenCalledTimes(1);
  });

  it("highlights the backend current state", () => {
    render(
      <AlignmentStateMachineView
        source={withAlignment({ currentState: "S2" })}
        onReEngage={vi.fn()}
      />,
    );
    expect(screen.getByText(/현재 상태:/)).toHaveTextContent("S2");
  });
});
