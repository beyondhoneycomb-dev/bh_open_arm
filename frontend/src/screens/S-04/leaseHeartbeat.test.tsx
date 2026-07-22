// CG-G-S04d: lease-remaining and heartbeat margin are shown ALWAYS. If the lease
// is not visible the operator cannot see an auto-hold coming (U-4). The bar is
// unconditionally mounted by the screen and renders both figures in every state —
// held, expired, stale — so it is never hidden behind a mode.

import { render, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ManualScreen from "./screen";
import { LeaseHeartbeatBar } from "./LeaseHeartbeatBar";
import { defaultManualSource } from "./manualSource";
import { sourceWith } from "./harness";

describe("CG-G-S04d lease-remaining + heartbeat margin shown always", () => {
  it("renders both figures from the foundation lease logic", () => {
    const { container } = render(<LeaseHeartbeatBar source={defaultManualSource()} />);
    const bar = container.querySelector(".oa-man-lease") as HTMLElement;
    // expiry 5000 - nowServer 1000 = 4000 ms; timeout 200 - (1100-1000) = 100 ms.
    expect(within(bar).getByText(/리스 잔여: 4000 ms/)).toBeInTheDocument();
    expect(within(bar).getByText(/하트비트 여유: 100 ms/)).toBeInTheDocument();
  });

  it("still shows the bar when the lease has expired", () => {
    const expired = sourceWith({
      lease: {
        sessionId: "s",
        leaseGeneration: 1,
        expiryMonoServer: 500,
        sequence: 1,
        issuedMonoClient: 400,
      },
    });
    const { container } = render(<LeaseHeartbeatBar source={expired} />);
    const bar = container.querySelector(".oa-man-lease") as HTMLElement;
    expect(bar.getAttribute("data-lease-held")).toBe("false");
    expect(within(bar).getByText(/리스 잔여: 0 ms/)).toBeInTheDocument();
    expect(container.querySelector('[data-field="heartbeat-margin"]')).not.toBeNull();
  });

  it("is present in the full screen regardless of arm state", () => {
    const { container } = render(<ManualScreen />);
    expect(container.querySelector('[data-field="lease-remaining"]')).not.toBeNull();
    expect(container.querySelector('[data-field="heartbeat-margin"]')).not.toBeNull();
  });
});
