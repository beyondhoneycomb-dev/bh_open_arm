import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HandoffProgress } from "./HandoffProgress";
import { beginHandoff, failCurrentStep } from "./handoff";

describe("HandoffProgress (FR-GUI-082, CG-G-04c)", () => {
  it("shows all four steps and each step's fail point", () => {
    render(<HandoffProgress state={beginHandoff()} />);
    expect(screen.getByText(/① 현 소유자 명령 중단/)).toBeInTheDocument();
    expect(screen.getByText(/② STOP_HOLD 유지/)).toBeInTheDocument();
    expect(screen.getByText(/③ 신규 소유자 권리 획득/)).toBeInTheDocument();
    expect(screen.getByText(/④ 첫 명령 검증/)).toBeInTheDocument();
    // Every step surfaces WHERE it can fail, before any has failed.
    expect(screen.getAllByText(/실패 지점:/)).toHaveLength(4);
  });

  it("states the CAN stream is held across the hand-off", () => {
    render(<HandoffProgress state={beginHandoff()} />);
    expect(screen.getByRole("note")).toHaveTextContent(/단절 없음/);
  });

  it("renders a failed step's fail point and the degraded STOP_HOLD stream", () => {
    render(<HandoffProgress state={failCurrentStep(beginHandoff())} />);
    expect(screen.getByText(/현 소유자가 권리를 놓지 않음/)).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(/STOP_HOLD/);
  });
});
