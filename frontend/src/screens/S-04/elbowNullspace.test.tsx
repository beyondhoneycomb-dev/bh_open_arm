// CG-G-S04i: operating the elbow slider moves the elbow with 0 EE movement in the
// 3D. The redundancy is nullspace: the intent HOLDS the EE (eeHold, zero XYZ/RPY
// delta), so the backend moves the elbow while the EE stays put — and the reused
// viewport, which renders the EE from backend FK, shows it unchanged. The facade
// proof is the command contract: the elbow intent's EE delta is exactly zero.

import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ManualScreen from "./screen";
import { ElbowSlider } from "./ElbowSlider";
import type { ManualCommand } from "./commands";
import { RecordingSink } from "./harness";

describe("CG-G-S04i elbow slider is a nullspace move that holds the EE", () => {
  it("emits a nullspace intent with zero EE translation and rotation delta", () => {
    const sink: ManualCommand[] = [];
    const { container } = render(
      <ElbowSlider
        side="right"
        value={0}
        onValueChange={vi.fn()}
        onCommand={(command) => sink.push(command)}
      />,
    );
    const slider = container.querySelector('[data-field="elbow-swivel"]') as Element;
    fireEvent.change(slider, { target: { value: "0.5" } });

    expect(sink).toHaveLength(1);
    expect(sink[0]).toEqual({
      op: "jog_nullspace",
      side: "right",
      elbowDelta: 0.5,
      eeHold: true,
      eeDeltaXyzMm: [0, 0, 0],
      eeDeltaRpyDeg: [0, 0, 0],
    });
  });

  it("states EE movement is zero", () => {
    const { getByText } = render(
      <ElbowSlider side="right" value={0} onValueChange={vi.fn()} onCommand={vi.fn()} />,
    );
    expect(getByText(/EE 이동 0/)).toBeInTheDocument();
  });

  it("through the armed screen the elbow intent still carries a zero EE delta", () => {
    const sink = new RecordingSink();
    const { container } = render(<ManualScreen commandSink={sink} />);
    fireEvent.click(container.querySelector('[data-field="arm-toggle"]') as Element);

    const slider = container.querySelector('[data-field="elbow-swivel"]') as Element;
    fireEvent.change(slider, { target: { value: "-0.3" } });

    const nullspace = sink.sent.find((command) => command.op === "jog_nullspace");
    expect(nullspace).toMatchObject({ eeHold: true, eeDeltaXyzMm: [0, 0, 0] });
  });
});
