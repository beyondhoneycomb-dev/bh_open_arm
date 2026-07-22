// CG-G-S05a: the C-Lat display carries a STANDING note that headset-internal latency
// is NOT included, because C-Lat is the control-channel latency only. Without the note
// an operator reads C-Lat as the whole loop, which it is not.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CLatView, HEADSET_INTERNAL_LATENCY_NOTE } from "./CLatView";
import { defaultTeleopSource } from "./teleopSource";

describe("CLatView (CG-G-S05a)", () => {
  it("shows the headset-internal-latency-not-included note at all times", () => {
    render(<CLatView cLat={defaultTeleopSource().cLat} />);
    const note = screen.getByText(HEADSET_INTERNAL_LATENCY_NOTE);
    expect(note).toBeInTheDocument();
    expect(note.textContent).toContain("헤드셋 내부 지연 미포함");
    expect(note.textContent).toContain("제어채널");
  });

  it("labels the section as the control-channel latency", () => {
    render(<CLatView cLat={defaultTeleopSource().cLat} />);
    expect(screen.getByRole("heading", { name: /제어채널 지연/ })).toBeInTheDocument();
  });

  it("renders each stage value without flattening unknown stages to a number", () => {
    render(<CLatView cLat={defaultTeleopSource().cLat} />);
    // The unknown motor stage must read as unmeasured, not 0.
    expect(screen.getByText("모터(DAMIAO) 명령 → 축 반응").closest("li")).toHaveTextContent("[미측정]");
    // The measured IK stage carries its measured value.
    expect(screen.getByText("IK solve (openarm_control)").closest("li")).toHaveTextContent("0.355 ms");
  });
});
