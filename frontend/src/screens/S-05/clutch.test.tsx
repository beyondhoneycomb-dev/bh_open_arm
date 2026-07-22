// CG-G-S05c: the clutch state is shown at all times, and on release->re-grip the
// delta starts at 0 (verified on screen). The screen renders the backend's re-grip
// deltas; the invariant is that a freshly re-captured reference yields a zero delta.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ClutchBadge } from "./ClutchBadge";
import { defaultTeleopSource, type ClutchStatus } from "./teleopSource";

function clutch(overrides: Partial<ClutchStatus>): ClutchStatus {
  return { ...defaultTeleopSource().clutch, ...overrides };
}

describe("ClutchBadge (CG-G-S05c)", () => {
  it("always shows the clutch engagement state", () => {
    render(<ClutchBadge clutch={clutch({ engaged: false })} />);
    const state = screen.getByText(/상태:/);
    expect(state).toHaveTextContent("해제");
    expect(state).toHaveAttribute("data-engaged", "false");
  });

  it("shows a re-grip delta of exactly 0 at the re-grip instant", () => {
    render(
      <ClutchBadge
        clutch={clutch({ engaged: true, referenceLatched: true, regripDeltaPosMm: 0, regripDeltaRotDeg: 0 })}
      />,
    );
    expect(screen.getByText("0.0 mm")).toBeInTheDocument();
    expect(screen.getByText("0.0°")).toBeInTheDocument();
  });

  it("reflects the engaged state visually via data-engaged", () => {
    render(<ClutchBadge clutch={clutch({ engaged: true })} />);
    expect(screen.getByText(/상태:/)).toHaveAttribute("data-engaged", "true");
  });
});
