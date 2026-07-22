// CG-G-S04f: in continuous (hold-to-move) mode, releasing the button stops
// immediately. Press emits a jog intent; release emits STOP_HOLD synchronously in
// the same handler — no timer, no debounce — so letting go is an immediate Cat 2
// hold (FR-MAN-009). The stop CATEGORY is the backend's; the screen only sends the
// release edge. Pointer-leave counts as a release too (dragging off the button).

import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { JogPanel } from "./JogPanel";
import type { ManualCommand } from "./commands";
import { defaultManualSource } from "./manualSource";

function renderContinuous(mode: "continuous" | "step", sink: ManualCommand[]) {
  const noop = () => {};
  return render(
    <JogPanel
      source={defaultManualSource()}
      mode={mode}
      onModeChange={noop}
      stepSizeDeg={5}
      onStepSizeChange={noop}
      speedScalePct={10}
      onSpeedScaleChange={noop}
      canMove
      onCommand={(command) => sink.push(command)}
    />,
  );
}

describe("CG-G-S04f continuous release stops immediately", () => {
  it("emits jog on press then STOP_HOLD on release, in order", () => {
    const sink: ManualCommand[] = [];
    const { container } = renderContinuous("continuous", sink);
    const plus = container.querySelector('[data-joint="1"][data-direction="positive"]') as Element;

    fireEvent.pointerDown(plus);
    expect(sink.at(-1)).toMatchObject({ op: "jog_joint", mode: "continuous" });

    fireEvent.pointerUp(plus);
    expect(sink.at(-1)).toEqual({ op: "stop_hold", side: "right" });
  });

  it("treats pointer-leave as a release (STOP_HOLD)", () => {
    const sink: ManualCommand[] = [];
    const { container } = renderContinuous("continuous", sink);
    const plus = container.querySelector('[data-joint="1"][data-direction="positive"]') as Element;

    fireEvent.pointerDown(plus);
    fireEvent.pointerLeave(plus);
    expect(sink.at(-1)).toEqual({ op: "stop_hold", side: "right" });
  });

  it("in step mode a click jogs one step and does not emit a release stop", () => {
    const sink: ManualCommand[] = [];
    const { container } = renderContinuous("step", sink);
    const plus = container.querySelector('[data-joint="1"][data-direction="positive"]') as Element;

    fireEvent.pointerDown(plus);
    fireEvent.click(plus);
    fireEvent.pointerUp(plus);

    expect(sink.filter((command) => command.op === "stop_hold")).toEqual([]);
    expect(sink.some((command) => command.op === "jog_joint" && command.mode === "step")).toBe(true);
  });
});
