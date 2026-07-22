// The event-log view (FR-SAF-065): it renders backend ring-buffer events and,
// for a latched event, offers an acknowledge that emits an intent (FR-SAF-043).
// The row stays marked latched — the backend clears the latch, not the screen.

import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EventLog } from "./EventLog";
import type { SafetyEvent } from "./source";

function event(overrides: Partial<SafetyEvent> = {}): SafetyEvent {
  return {
    id: "e-1",
    tMonoMs: 1000,
    cause: "residual breach: joint2",
    reaction: "STOP_HOLD",
    latched: true,
    joints: ["openarm_left_joint2"],
    ...overrides,
  };
}

describe("EventLog", () => {
  it("marks a latched event and acknowledges via intent", () => {
    const onAcknowledgeEvent = vi.fn();
    const { container } = render(
      <EventLog events={[event()]} nowMonoMs={2000} onAcknowledgeEvent={onAcknowledgeEvent} />,
    );
    const row = container.querySelector('[data-event="e-1"]')!;
    expect(row.getAttribute("data-latched")).toBe("true");
    fireEvent.click(container.querySelector('[data-action="ack-event"]')!);
    expect(onAcknowledgeEvent).toHaveBeenCalledWith("e-1");
  });

  it("offers no ack for an unlatched event", () => {
    const { container } = render(
      <EventLog
        events={[event({ latched: false })]}
        nowMonoMs={2000}
        onAcknowledgeEvent={() => {}}
      />,
    );
    expect(container.querySelector('[data-action="ack-event"]')).toBeNull();
  });

  it("renders an empty state with no events", () => {
    const { getByText } = render(
      <EventLog events={[]} nowMonoMs={0} onAcknowledgeEvent={() => {}} />,
    );
    expect(getByText("이벤트 없음")).toBeInTheDocument();
  });
});
