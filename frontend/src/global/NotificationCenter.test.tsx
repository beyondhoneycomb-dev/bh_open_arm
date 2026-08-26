import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useState } from "react";

import { NotificationBadge, NotificationCenter } from "./NotificationCenter";
import { acknowledge, type Notification } from "./notifications";
import { Severity } from "./contracts/errorCodes";

// A tiny harness that holds the notification list in React state so acking in the
// center flows back to the badge, mirroring how the shell wires the two.
function Harness({ initial }: { initial: Notification[] }) {
  const [items, setItems] = useState(initial);
  return (
    <div>
      <NotificationBadge notifications={items} />
      <NotificationCenter notifications={items} onAck={(id) => setItems(acknowledge(items, id))} />
    </div>
  );
}

function errorAlert(id: string): Notification {
  return {
    id,
    code: "OA-CAN-001",
    severity: Severity.ERROR,
    source: "OA-CAN",
    timestamp: Date.now(),
    detail: "이중 bind 감지",
    blocking: true,
    acked: false,
  };
}

describe("NotificationCenter (CG-G-03g render): badge held until ack", () => {
  it("holds the badge while an ERROR alert is unacknowledged, then clears on ack", () => {
    render(<Harness initial={[errorAlert("e1")]} />);
    const badge = screen.getByRole("status", { name: /미확인 경고/ });
    expect(badge).toHaveAttribute("data-alert-held", "true");

    fireEvent.click(screen.getByRole("button", { name: "확인" }));

    const cleared = screen.getByRole("status", { name: /경고 없음/ });
    expect(cleared).toHaveAttribute("data-alert-held", "false");
  });

  it("does not hold the badge for an alert that stopped nothing", () => {
    // Severity is rendered, not consulted: this row is an ERROR and still asks for no
    // click, because nothing is waiting on the operator to release it.
    const logged: Notification = { ...errorAlert("l1"), blocking: false };
    render(<NotificationBadge notifications={[logged]} />);
    expect(screen.getByRole("status")).toHaveAttribute("data-alert-held", "false");
  });

  it("holds the badge for a WARN that stopped something", () => {
    const warnLatch: Notification = { ...errorAlert("w1"), severity: Severity.WARN };
    render(<NotificationBadge notifications={[warnLatch]} />);
    expect(screen.getByRole("status")).toHaveAttribute("data-alert-held", "true");
  });
});
