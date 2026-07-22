// CG-G-S09d: the six dry-run checks render PER ITEM (with violation detail), and
// the real-send button is HARD-BLOCKED until all six pass. A pre-run (null) report
// renders every item as not_run and blocks send; a full-pass report enables it.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DryRunReport } from "./DryRunReport";
import { DRY_RUN_CHECKS, type DryRunReport as DryRunReportData } from "./simDomain";

function fullPassReport(): DryRunReportData {
  return { checks: DRY_RUN_CHECKS.map((meta) => ({ id: meta.id, status: "pass" as const })) };
}

describe("DryRunReport (CG-G-S09d)", () => {
  it("renders all six checks per item, including a not_run pre-run state", () => {
    render(<DryRunReport report={null} controlTarget="real" onSendToReal={vi.fn()} />);
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(6);
    for (const meta of DRY_RUN_CHECKS) {
      const item = document.querySelector(`[data-check="${meta.id}"]`);
      expect(item).not.toBeNull();
      expect(item).toHaveAttribute("data-status", "not_run");
    }
  });

  it("shows a failed check's violation detail per item", () => {
    const report: DryRunReportData = {
      checks: DRY_RUN_CHECKS.map((meta) =>
        meta.id === "torque"
          ? {
              id: meta.id,
              status: "fail" as const,
              violation: { joint: "left_joint2", simTimeS: 1.4, overshoot: "6 Nm" },
            }
          : { id: meta.id, status: "pass" as const },
      ),
    };
    render(<DryRunReport report={report} controlTarget="real" onSendToReal={vi.fn()} />);
    const torque = document.querySelector('[data-check="torque"]') as HTMLElement;
    expect(torque).toHaveAttribute("data-status", "fail");
    expect(torque).toHaveTextContent("left_joint2");
    expect(torque).toHaveTextContent("6 Nm");
  });

  it("blocks real-send while any check is not passed", () => {
    const onSendToReal = vi.fn();
    render(<DryRunReport report={null} controlTarget="real" onSendToReal={onSendToReal} />);
    expect(screen.getByRole("alert")).toHaveTextContent(/실기 전송 하드 차단/);
    const send = screen.getByRole("button", { name: "실기 전송" });
    expect(send).toBeDisabled();
    fireEvent.click(send);
    expect(onSendToReal).not.toHaveBeenCalled();
  });

  it("bypass stays gated behind an explicit confirmation while not passed", () => {
    const onSendToReal = vi.fn();
    render(<DryRunReport report={null} controlTarget="real" onSendToReal={onSendToReal} />);
    const override = screen.getByRole("button", { name: "우회 전송 (확인됨)" });
    expect(override).toBeDisabled();
    fireEvent.click(override);
    expect(onSendToReal).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("checkbox"));
    expect(override).toBeEnabled();
    fireEvent.click(override);
    expect(onSendToReal).toHaveBeenCalledTimes(1);
  });

  it("enables real-send once all six checks pass", () => {
    const onSendToReal = vi.fn();
    render(
      <DryRunReport report={fullPassReport()} controlTarget="real" onSendToReal={onSendToReal} />,
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    const send = screen.getByRole("button", { name: "실기 전송" });
    expect(send).toBeEnabled();
    fireEvent.click(send);
    expect(onSendToReal).toHaveBeenCalledTimes(1);
  });
});
