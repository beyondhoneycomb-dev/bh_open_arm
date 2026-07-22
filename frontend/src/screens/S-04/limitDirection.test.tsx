// CG-G-S04c: at a limit, the button for that direction is disabled and only the
// opposite is allowed. The "which direction is blocked" verdict is the backend's
// (blockedDirection on the joint readout); the screen renders it and never
// recomputes at-limit from the position, which would be a second clamp.

import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { JogPanel } from "./JogPanel";
import { defaultManualSource, type JointReadout } from "./manualSource";

function sourceWithJointBlocked(index: number, blocked: JointReadout["blockedDirection"]) {
  const base = defaultManualSource();
  const joints = base.joints.map((joint) =>
    joint.index === index ? { ...joint, blockedDirection: blocked } : joint,
  );
  return { ...base, joints };
}

function renderPanel(source: ReturnType<typeof defaultManualSource>, canMove: boolean) {
  return render(
    <JogPanel
      source={source}
      mode="continuous"
      onModeChange={vi.fn()}
      stepSizeDeg={1}
      onStepSizeChange={vi.fn()}
      speedScalePct={10}
      onSpeedScaleChange={vi.fn()}
      canMove={canMove}
      onCommand={vi.fn()}
    />,
  );
}

describe("CG-G-S04c limit-reached direction is disabled, opposite allowed", () => {
  it("disables the + button at the upper limit and leaves − enabled", () => {
    const { container } = renderPanel(sourceWithJointBlocked(1, "positive"), true);
    const plus = container.querySelector('[data-joint="1"][data-direction="positive"]');
    const minus = container.querySelector('[data-joint="1"][data-direction="negative"]');
    expect(plus).toBeDisabled();
    expect(minus).toBeEnabled();
  });

  it("disables the − button at the lower limit and leaves + enabled", () => {
    const { container } = renderPanel(sourceWithJointBlocked(3, "negative"), true);
    const plus = container.querySelector('[data-joint="3"][data-direction="positive"]');
    const minus = container.querySelector('[data-joint="3"][data-direction="negative"]');
    expect(plus).toBeEnabled();
    expect(minus).toBeDisabled();
  });

  it("leaves an unblocked joint's both directions enabled", () => {
    const { container } = renderPanel(sourceWithJointBlocked(1, "positive"), true);
    const plus = container.querySelector('[data-joint="2"][data-direction="positive"]');
    const minus = container.querySelector('[data-joint="2"][data-direction="negative"]');
    expect(plus).toBeEnabled();
    expect(minus).toBeEnabled();
  });
});
