// CG-G-S12a (render half): the selector pre-selects STOP_HOLD by default and
// never the power-cut policy, tags the load-dropping policies, and emits the
// operator's choice as an intent.

import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ReactionPolicySelector } from "./ReactionPolicySelector";

function radio(container: HTMLElement, mode: string): HTMLInputElement {
  return container.querySelector<HTMLInputElement>(
    `[data-reaction-option="${mode}"] input[type="radio"]`,
  )!;
}

describe("CG-G-S12a: reaction selector default", () => {
  it("selects STOP_HOLD when the backend reports no mode, and never POWER_OFF", () => {
    const { container } = render(
      <ReactionPolicySelector backendMode={null} onSelectReaction={() => {}} />,
    );
    expect(radio(container, "STOP_HOLD").checked).toBe(true);
    expect(radio(container, "POWER_OFF").checked).toBe(false);
  });

  it("reflects the backend mode when one is reported", () => {
    const { container } = render(
      <ReactionPolicySelector backendMode="RETRACT" onSelectReaction={() => {}} />,
    );
    expect(radio(container, "RETRACT").checked).toBe(true);
    expect(radio(container, "STOP_HOLD").checked).toBe(false);
  });

  it("tags the load-dropping policies with a drop warning", () => {
    const { container } = render(
      <ReactionPolicySelector backendMode="STOP_HOLD" onSelectReaction={() => {}} />,
    );
    expect(container.querySelector('[data-drop-warning="POWER_OFF"]')).not.toBeNull();
    expect(container.querySelector('[data-drop-warning="STOP_DECEL"]')).not.toBeNull();
    expect(container.querySelector('[data-drop-warning="STOP_HOLD"]')).toBeNull();
  });

  it("emits the chosen policy as an intent", () => {
    const onSelectReaction = vi.fn();
    const { container } = render(
      <ReactionPolicySelector backendMode="STOP_HOLD" onSelectReaction={onSelectReaction} />,
    );
    fireEvent.click(radio(container, "GRAVITY_COMP"));
    expect(onSelectReaction).toHaveBeenCalledWith("GRAVITY_COMP");
  });
});
