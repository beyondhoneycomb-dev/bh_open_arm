import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ModeAuthorityTable } from "./ModeAuthorityTable";

describe("ModeAuthorityTable (FR-GUI-080)", () => {
  it("renders one body row per mode", () => {
    render(<ModeAuthorityTable activeMode="IDLE" />);
    const table = screen.getByRole("table", { name: "8모드 제어권 표" });
    const bodyRows = within(table).getAllByRole("row").slice(1);
    expect(bodyRows).toHaveLength(8);
  });

  it("shows that only MOTOR_SETUP permits an external CAN client (CG-G-04e)", () => {
    render(<ModeAuthorityTable activeMode="IDLE" />);
    const motorSetupRow = screen.getByRole("row", { name: /MOTOR_SETUP/ });
    expect(within(motorSetupRow).getByText(/허용 \(CAN 미점유\)/)).toBeInTheDocument();
    const manualRow = screen.getByRole("row", { name: /MANUAL/ });
    expect(within(manualRow).getByText("불가")).toBeInTheDocument();
  });

  it("marks the active mode", () => {
    render(<ModeAuthorityTable activeMode="INFERENCE" />);
    const activeRow = screen.getByRole("row", { name: /INFERENCE/ });
    expect(activeRow).toHaveAttribute("aria-current", "true");
  });
});
