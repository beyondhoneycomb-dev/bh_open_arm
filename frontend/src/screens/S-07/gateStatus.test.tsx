// Graceful 3C-gate handling: the WP-3C gates are not built yet, so S-07 renders
// their state honestly (pending / unavailable / degraded_accepted) and fabricates
// no verdict. This proves the reduced/pending badge renders and carries the state.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { GateStatusView } from "./GateStatusView";
import { pendingThreeCGates } from "./collectSource";

describe("GateStatusView (graceful 3C gates)", () => {
  it("renders PG-STO-001 and the interlock/crash gates as pending", () => {
    render(<GateStatusView gates={pendingThreeCGates()} />);
    const gate = screen.getByTestId("gate-PG-STO-001");
    expect(gate).toHaveTextContent("PG-STO-001");
    expect(gate.querySelector('[data-state="pending"]')).not.toBeNull();
  });

  it("renders a landed DEGRADED_ACCEPTED verdict as a reduced badge, not a failure", () => {
    render(
      <GateStatusView
        gates={[
          { id: "PG-STO-001", label: "저장 무결성", state: "degraded_accepted", detail: null },
        ]}
      />,
    );
    const badge = screen.getByTestId("gate-PG-STO-001").querySelector("[data-state]");
    expect(badge).toHaveAttribute("data-state", "degraded_accepted");
    expect(badge).toHaveTextContent("축소 수용");
  });
});
