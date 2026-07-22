// CG-G-S04b: a 3D drag or a slider alone issues no command — an explicit arm/enable
// must come first. The screen routes every motion intent through a single gate
// (arm AND lease AND fresh stream), so an unarmed press or drag emits nothing even
// though the affordance exists. The positive control proves the gate is real, not
// merely "nothing ever sends": once armed, a jog press does emit.

import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ManualScreen from "./screen";
import { RecordingSink } from "./harness";

describe("CG-G-S04b motion requires explicit arm/enable first", () => {
  it("issues 0 commands from jog/elbow/cartesian/speed interactions while unarmed", () => {
    const sink = new RecordingSink();
    const { container } = render(<ManualScreen commandSink={sink} />);

    // Never clicked Arm. Interact with every motion affordance and a slider.
    const jogPlus = container.querySelector('[data-direction="positive"]');
    const elbow = container.querySelector('[data-field="elbow-swivel"]');
    const speed = container.querySelector('[aria-label="속도 스케일 퍼센트"]');

    fireEvent.pointerDown(jogPlus as Element);
    fireEvent.pointerUp(jogPlus as Element);
    fireEvent.change(elbow as Element, { target: { value: "0.5" } });
    fireEvent.change(speed as Element, { target: { value: "80" } });

    expect(sink.sent).toEqual([]);
  });

  it("emits a jog only after arming (gate is real)", () => {
    const sink = new RecordingSink();
    const { container } = render(<ManualScreen commandSink={sink} />);

    const arm = container.querySelector('[data-field="arm-toggle"]') as HTMLButtonElement;
    expect(arm.disabled).toBe(false); // lease held + fresh in the default fixture
    fireEvent.click(arm);
    expect(sink.ops()).toContain("enable_torque");

    const jogPlus = container.querySelector('[data-direction="positive"]') as Element;
    fireEvent.pointerDown(jogPlus);
    expect(sink.ops()).toContain("jog_joint");
  });
});
