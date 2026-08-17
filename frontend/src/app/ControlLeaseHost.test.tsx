// The shell's lease surface: what it renders while a client is live, and while there is none.
//
// This is the first thing in the build to draw live realtime state. What it must never do is
// render an absent channel as a quiet one — `client: null` and "connected, no lease yet" produce
// the same empty lease, and only one of them means the operator could take control by asking.

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ControlLeaseHost } from "./ControlLeaseHost";
import { RealtimeProvider } from "./RealtimeContext";
import type { LeaseSnapshot } from "../ws/leaseRenewer";

const HELD: LeaseSnapshot = {
  status: "held",
  sessionId: "s-1",
  generation: 3,
  sequence: 7,
  expiryMonoServer: Number.MAX_SAFE_INTEGER,
  lastRejectReason: null,
};

function clientWith(snapshot: LeaseSnapshot) {
  return {
    start: vi.fn(),
    dispose: vi.fn(),
    lease: { snapshot: () => snapshot },
  };
}

function renderIn(client: unknown) {
  return render(
    <RealtimeProvider createClient={() => client as never}>
      <ControlLeaseHost />
    </RealtimeProvider>,
  );
}

describe("ControlLeaseHost", () => {
  it("renders the held lease the client reports", () => {
    renderIn(clientWith(HELD));

    expect(screen.getByText("s-1")).toBeTruthy();
    expect(screen.getByText("제어권 보유 (controlling)")).toBeTruthy();
  });

  it("renders an observer as an observer even with a lease present", () => {
    // A latched arm still carries the lease fields. Drawing it as controlling would show
    // authority the server refuses to act on.
    renderIn(clientWith({ ...HELD, status: "latched" }));

    expect(screen.getByText("관찰자 / 권리 없음 (observer)")).toBeTruthy();
  });

  it("says there is no channel rather than drawing an empty lease", () => {
    // The failure this exists for: no client and no lease look identical in the data, and the
    // difference is whether asking for control could work at all.
    const failing = { start: vi.fn(), dispose: vi.fn(), lease: { snapshot: () => HELD } };
    failing.start.mockImplementation(() => {
      throw new Error("no socket");
    });

    renderIn(failing);

    expect(screen.getByTestId("realtime-absent")).toBeTruthy();
    expect(screen.queryByText("s-1")).toBeNull();
  });

  it("shows a refusal the view has no label for, in the server's own words", () => {
    // `rejected_latched` is the one an operator most needs: it says the arm is held and a
    // re-arm is owed. The view labels five verdicts and this is not one of them.
    renderIn(clientWith({ ...HELD, lastRejectReason: "rejected_latched" }));

    expect(screen.getByText(/rejected_latched/)).toBeTruthy();
  });
});
