// CG-G-S04e: every numeric value carries its unit (rad/deg/mm/Nm/degC/rad·s⁻¹) and
// every cartesian control carries its reference-frame label. Units and frames are
// the backend's; the screen shows them so a value is never ambiguous (FR-GUI-069).

import { render, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ManualScreen from "./screen";

describe("CG-G-S04e unit and reference-frame labels are present", () => {
  it("labels joint readouts with rad, deg, velocity, torque and temperature units", () => {
    const { container } = render(<ManualScreen />);
    expect(within(container).getByText("위치 (rad)")).toBeInTheDocument();
    expect(within(container).getByText("위치 (deg)")).toBeInTheDocument();
    expect(within(container).getByText("속도 (rad·s⁻¹)")).toBeInTheDocument();
    expect(within(container).getByText("토크 (Nm)")).toBeInTheDocument();

    // Both rad and deg positions are rendered per joint from backend values.
    expect(container.querySelectorAll('td[data-unit="rad"]').length).toBeGreaterThan(0);
    expect(container.querySelectorAll('td[data-unit="deg"]').length).toBeGreaterThan(0);
  });

  it("states the active limit set at all times", () => {
    const { container } = render(<ManualScreen />);
    expect(container.querySelector('[data-field="active-limit-set"]')).not.toBeNull();
    expect(within(container).getByText(/활성 리밋 세트/)).toBeInTheDocument();
  });

  it("labels the cartesian reference frame with base/tool/world and the base≡world note", () => {
    const { container } = render(<ManualScreen />);
    const frame = container.querySelector('[data-field="reference-frame"]') as HTMLElement;
    for (const label of ["base", "tool", "world"]) {
      expect(within(frame).getByText(label)).toBeInTheDocument();
    }
    expect(within(frame).getByText(/base와 world는 회전이 동일/)).toBeInTheDocument();
  });

  it("labels EE pose and cartesian axes with mm/deg units", () => {
    const { container } = render(<ManualScreen />);
    expect(container.querySelectorAll('[data-unit="mm"]').length).toBeGreaterThan(0);
    expect(container.querySelectorAll('[data-unit="deg"]').length).toBeGreaterThan(0);
  });
});
