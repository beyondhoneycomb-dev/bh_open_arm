// CG-G-S07c: WS-transmit drops and capture/encode drops render in two SEPARATE
// regions, each with its own total and its own drop-rate flag (CG-G-S07d) — never
// merged into one figure, which would hide whether the cause was preview or capture.

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DropReportView } from "./DropReportView";
import type { DropReport } from "./types";

// 3 WS drops over 100 frames -> warn band; 6 capture drops -> overload band. The two
// sides land in different bands, which only distinguishes them because they are kept
// apart.
const REPORT: DropReport = {
  frameCount: 100,
  wsTransmit: [
    { channel: "camera_preview", dropCount: 2, classification: "normal" },
    { channel: "telemetry", dropCount: 1, classification: "normal" },
  ],
  camera: [{ slot: "left_wrist", missingRows: 3, frameNumberGaps: 2 }],
  can: { flaggedFrames: 1, suspectedStaleFrames: 0 },
};

describe("DropReportView (CG-G-S07c / S07d)", () => {
  it("renders WS-transmit and capture/encode as two separate regions", () => {
    render(<DropReportView report={REPORT} />);
    expect(screen.getByTestId("drop-ws-transmit")).toBeInTheDocument();
    expect(screen.getByTestId("drop-capture-encode")).toBeInTheDocument();
  });

  it("keeps the two totals distinct (never one merged number)", () => {
    render(<DropReportView report={REPORT} />);
    expect(screen.getByTestId("drop-ws-total")).toHaveTextContent("3"); // 2 + 1
    expect(screen.getByTestId("drop-capture-total")).toHaveTextContent("6"); // 3 + 2 + 1
  });

  it("flags each side independently against the display bands", () => {
    render(<DropReportView report={REPORT} />);
    const ws = within(screen.getByTestId("drop-ws-transmit"));
    const capture = within(screen.getByTestId("drop-capture-encode"));
    expect(ws.getByRole("status")).toHaveAttribute("data-flag", "warn");
    expect(capture.getByRole("status")).toHaveAttribute("data-flag", "overload");
  });
});
