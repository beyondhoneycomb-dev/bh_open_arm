import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ControlLeaseView } from "./ControlLeaseView";
import type { ControlLease, LeaseClock } from "./lease";

const ACTIVE_LEASE: ControlLease = {
  sessionId: "sess-A",
  leaseGeneration: 5,
  expiryMonoServer: 10_000,
  sequence: 100,
  issuedMonoClient: 50_000,
};

function clock(nowMonoServer: number): LeaseClock {
  return { nowMonoServer, nowMonoClient: 0 };
}

describe("ControlLeaseView (FR-GUI-092, U-4)", () => {
  it("renders an operator with an active lease as controlling", () => {
    render(
      <ControlLeaseView lease={ACTIVE_LEASE} clock={clock(9_000)} role="operator" lastVerdict={null} />,
    );
    expect(screen.getByText(/제어권 보유 \(controlling\)/)).toBeInTheDocument();
    expect(screen.getByText("활성")).toBeInTheDocument();
    expect(screen.getByText(/1000 ms/)).toBeInTheDocument();
  });

  it("renders an expired lease as not controlling", () => {
    render(
      <ControlLeaseView lease={ACTIVE_LEASE} clock={clock(10_500)} role="operator" lastVerdict={null} />,
    );
    expect(screen.getByText(/관찰자 \/ 권리 없음/)).toBeInTheDocument();
    expect(screen.getByText("만료")).toBeInTheDocument();
  });

  it("never renders an observer as controlling even with an active lease", () => {
    render(
      <ControlLeaseView lease={ACTIVE_LEASE} clock={clock(9_000)} role="observer" lastVerdict={null} />,
    );
    expect(screen.getByText(/관찰자 \/ 권리 없음/)).toBeInTheDocument();
  });

  it("surfaces the last anti-replay reject reason", () => {
    render(
      <ControlLeaseView
        lease={ACTIVE_LEASE}
        clock={clock(9_000)}
        role="operator"
        lastVerdict="rejected_replay"
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(/시퀀스 역행\/중복 재생/);
  });
});
