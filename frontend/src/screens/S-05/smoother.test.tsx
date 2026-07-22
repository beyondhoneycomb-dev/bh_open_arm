// CG-G-S05d: min_cutoff / beta / d_cutoff are exposed at runtime and the theoretical
// phase lag tau = 1/(2π·f_c) is shown alongside min_cutoff. The tau VALUE is the
// backend's applied figure; the screen shows the formula label and that value, and
// ships changes as intents.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PHASE_LAG_FORMULA, SmootherParamForm } from "./SmootherParamForm";
import { defaultTeleopSource } from "./teleopSource";

describe("SmootherParamForm (CG-G-S05d)", () => {
  it("exposes all three One-Euro parameters", () => {
    render(<SmootherParamForm smoother={defaultTeleopSource().smoother} disabled={false} onChange={vi.fn()} />);
    expect(screen.getByLabelText("min_cutoff (Hz)")).toBeInTheDocument();
    expect(screen.getByLabelText("beta")).toBeInTheDocument();
    expect(screen.getByLabelText("d_cutoff (Hz)")).toBeInTheDocument();
  });

  it("shows the tau formula and the backend applied tau alongside min_cutoff", () => {
    render(<SmootherParamForm smoother={defaultTeleopSource().smoother} disabled={false} onChange={vi.fn()} />);
    const phaseLag = screen.getByText(new RegExp(PHASE_LAG_FORMULA.replace(/[()/]/g, "\\$&")));
    expect(phaseLag).toBeInTheDocument();
    // The applied theoretical tau for min_cutoff=2.0 Hz is ~79.6 ms (backend fact).
    expect(phaseLag).toHaveTextContent("79.6 ms");
    expect(phaseLag).toHaveTextContent("실측 아님");
  });

  it("ships a parameter change to the backend as an intent", () => {
    const onChange = vi.fn();
    render(<SmootherParamForm smoother={defaultTeleopSource().smoother} disabled={false} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("min_cutoff (Hz)"), { target: { value: "6" } });
    expect(onChange).toHaveBeenCalledWith(6, 0.04, 1.5);
  });

  it("disables the controls while a VR session holds the command source (CG-G-S05f)", () => {
    render(<SmootherParamForm smoother={defaultTeleopSource().smoother} disabled onChange={vi.fn()} />);
    expect(screen.getByLabelText("min_cutoff (Hz)")).toBeDisabled();
    expect(screen.getByLabelText("beta")).toBeDisabled();
    expect(screen.getByLabelText("d_cutoff (Hz)")).toBeDisabled();
  });
});
