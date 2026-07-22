// Runtime CG-G-S02c: the re-zero dialog forces all four steps in order — no later
// step's control is reachable until its predecessors complete — and yields the
// audit entry only after a reason is recorded. The embedded viewport takes its
// WebGL-absent fallback in jsdom.

import { fireEvent, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RezeroDialog } from "./RezeroDialog";

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(() => null);
});
afterEach(() => {
  vi.restoreAllMocks();
});

const JOINTS = ["openarm_left_joint1"] as const;

function renderDialog(onComplete = vi.fn()) {
  const result = render(
    <RezeroDialog
      side="left"
      jointNames={JOINTS}
      restPositionsRad={{ openarm_left_joint1: 0 }}
      currentPositionsRad={{ openarm_left_joint1: 0.01 }}
      nowMonoMs={7000}
      onComplete={onComplete}
    />,
  );
  return { ...result, onComplete };
}

describe("CG-G-S02c re-zero forces all four steps", () => {
  it("exposes only the current step's control, in order", () => {
    const { container } = renderDialog();
    expect(container.querySelector('[data-action="confirm-rest-pose"]')).not.toBeNull();
    expect(container.querySelector('[data-action="ack-new-zero"]')).toBeNull();
    expect(container.querySelector('[data-action="record-audit"]')).toBeNull();

    fireEvent.click(container.querySelector('[data-action="confirm-rest-pose"]') as HTMLButtonElement);
    expect(container.querySelector('[data-action="ack-new-zero"]')).not.toBeNull();
    expect(container.querySelector('[data-action="add-confirmation"]')).toBeNull();
  });

  it("needs both confirmations and an audit reason before it completes", () => {
    const { container, onComplete } = renderDialog();

    fireEvent.click(container.querySelector('[data-action="confirm-rest-pose"]') as HTMLButtonElement);
    fireEvent.click(container.querySelector('[data-action="ack-new-zero"]') as HTMLButtonElement);

    fireEvent.click(container.querySelector('[data-action="add-confirmation"]') as HTMLButtonElement);
    expect(container.querySelector('[data-action="add-confirmation"]')).not.toBeNull();
    expect(container.querySelector('[data-action="record-audit"]')).toBeNull();

    fireEvent.click(container.querySelector('[data-action="add-confirmation"]') as HTMLButtonElement);
    const record = container.querySelector<HTMLButtonElement>('[data-action="record-audit"]');
    expect(record).not.toBeNull();
    expect(record?.disabled).toBe(true);
    expect(onComplete).not.toHaveBeenCalled();

    fireEvent.change(container.querySelector('[data-input="audit-reason"]') as HTMLInputElement, {
      target: { value: "CAN 어댑터 교체" },
    });
    fireEvent.click(container.querySelector('[data-action="record-audit"]') as HTMLButtonElement);

    expect(container.querySelector('[data-rezero="complete"]')).not.toBeNull();
    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(onComplete.mock.calls[0][0]).toEqual({
      action: "hardware_swap_rezero",
      reason: "CAN 어댑터 교체",
      side: "left",
      monoMs: 7000,
    });
  });
});
