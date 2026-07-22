import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ModeBadge } from "./ModeBadge";

describe("ModeBadge (FR-GUI-080/082)", () => {
  it("shows the active mode and who holds send_action", () => {
    render(<ModeBadge mode="MANUAL" transitioning={false} />);
    expect(screen.getByLabelText("현재 모드")).toBeInTheDocument();
    expect(screen.getByText(/MANUAL/)).toBeInTheDocument();
    expect(screen.getByText(/send_action 권리: GUI 조그/)).toBeInTheDocument();
  });

  it("shows a held-stream transition indicator only while transitioning", () => {
    const { rerender } = render(<ModeBadge mode="TELEOP_VR" transitioning={false} />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    rerender(<ModeBadge mode="TELEOP_VR" transitioning={true} />);
    expect(screen.getByRole("alert")).toHaveTextContent(/STOP_HOLD/);
  });
});
