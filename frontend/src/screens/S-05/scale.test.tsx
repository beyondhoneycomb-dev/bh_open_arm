// CG-G-S05e: the rotation scale control is provided SEPARATELY from the position
// scale control. They are two distinct controls that never share a value, because
// joint6's ±45° limit forces the rotation channel to narrow on its own.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ScaleControls } from "./ScaleControls";
import { defaultTeleopSource } from "./teleopSource";

describe("ScaleControls (CG-G-S05e)", () => {
  it("renders position scale and rotation scale as two separate controls", () => {
    render(
      <ScaleControls
        scale={defaultTeleopSource().scale}
        disabled={false}
        onPositionScale={vi.fn()}
        onRotationScale={vi.fn()}
      />,
    );
    const position = screen.getByLabelText(/위치 스케일/);
    const rotation = screen.getByLabelText(/회전 스케일/);
    expect(position).toBeInTheDocument();
    expect(rotation).toBeInTheDocument();
    expect(position).not.toBe(rotation);
  });

  it("routes each control to its own independent intent", () => {
    const onPositionScale = vi.fn();
    const onRotationScale = vi.fn();
    render(
      <ScaleControls
        scale={defaultTeleopSource().scale}
        disabled={false}
        onPositionScale={onPositionScale}
        onRotationScale={onRotationScale}
      />,
    );
    fireEvent.change(screen.getByLabelText(/회전 스케일/), { target: { value: "0.5" } });
    expect(onRotationScale).toHaveBeenCalledWith(0.5);
    expect(onPositionScale).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText(/위치 스케일/), { target: { value: "1.2" } });
    expect(onPositionScale).toHaveBeenCalledWith(1.2);
  });

  it("gives the two channels distinct adjustable ranges (rotation bounded to <=1)", () => {
    const { scale } = defaultTeleopSource();
    render(
      <ScaleControls scale={scale} disabled={false} onPositionScale={vi.fn()} onRotationScale={vi.fn()} />,
    );
    expect(screen.getByLabelText(/위치 스케일/)).toHaveAttribute("max", String(scale.positionScaleMax));
    expect(screen.getByLabelText(/회전 스케일/)).toHaveAttribute("max", String(scale.rotationScaleMax));
    expect(scale.positionScaleMax).not.toBe(scale.rotationScaleMax);
  });
});
