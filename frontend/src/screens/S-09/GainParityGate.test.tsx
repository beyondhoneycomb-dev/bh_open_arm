// CG-G-S09b: starting twin / dry-run on the compliant (70-series) gain profile is
// REFUSED — both start controls are disabled and the parity-broken reason is shown.
// On stiff (230-series) the controls are enabled and no refusal appears.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { GainParityGate } from "./GainParityGate";

describe("GainParityGate (CG-G-S09b)", () => {
  it("refuses twin/dry-run on the compliant profile", () => {
    const onStartTwin = vi.fn();
    const onStartDryRun = vi.fn();
    render(
      <GainParityGate
        gainProfile="compliant"
        onStartTwin={onStartTwin}
        onStartDryRun={onStartDryRun}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(/게인 패리티 깨짐/);

    const twin = screen.getByRole("button", { name: "디지털 트윈 시작" });
    const dryRun = screen.getByRole("button", { name: "드라이런 시작" });
    expect(twin).toBeDisabled();
    expect(dryRun).toBeDisabled();

    fireEvent.click(twin);
    fireEvent.click(dryRun);
    expect(onStartTwin).not.toHaveBeenCalled();
    expect(onStartDryRun).not.toHaveBeenCalled();
  });

  it("allows twin/dry-run on the stiff profile with no refusal", () => {
    const onStartTwin = vi.fn();
    const onStartDryRun = vi.fn();
    render(
      <GainParityGate
        gainProfile="stiff"
        onStartTwin={onStartTwin}
        onStartDryRun={onStartDryRun}
      />,
    );

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    const twin = screen.getByRole("button", { name: "디지털 트윈 시작" });
    expect(twin).toBeEnabled();
    fireEvent.click(twin);
    fireEvent.click(screen.getByRole("button", { name: "드라이런 시작" }));
    expect(onStartTwin).toHaveBeenCalledTimes(1);
    expect(onStartDryRun).toHaveBeenCalledTimes(1);
  });
});
