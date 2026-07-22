// PG-VR-001 graceful handling: the hardware gate has not landed, so its verdict
// arrives as WS state that is currently "pending". The VR-session view renders that
// pending state as a badge and fabricates no verdict; a real `failed` shows the
// WebXR fallback as the operational path (WP-3B-08), not a faked one.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { VrSessionView } from "./VrSessionView";
import { defaultTeleopSource, type VrGate } from "./teleopSource";

function gate(status: VrGate["status"]): VrGate {
  return { id: "PG-VR-001", status, note: `note-${status}` };
}

describe("VrSessionView PG-VR-001 handling", () => {
  it("renders the pending gate as pending, not a fabricated pass or fail", () => {
    render(<VrSessionView session={defaultTeleopSource().session} gate={gate("pending")} />);
    const badge = screen.getByText(/PG-VR-001:/);
    expect(badge).toHaveAttribute("data-status", "pending");
    expect(badge).toHaveTextContent("대기");
    const path = screen.getByText(/운영 경로:/);
    expect(path).toHaveAttribute("data-path", "pending");
    expect(path).toHaveAttribute("data-fallback", "false");
  });

  it("shows the WebXR fallback as operational when the gate fails", () => {
    render(<VrSessionView session={defaultTeleopSource().session} gate={gate("failed")} />);
    const path = screen.getByText(/운영 경로:/);
    expect(path).toHaveAttribute("data-path", "webxr_fallback");
    expect(path).toHaveAttribute("data-fallback", "true");
    expect(path).toHaveTextContent("WebXR");
  });

  it("keeps the native APK path when the gate passes", () => {
    render(<VrSessionView session={defaultTeleopSource().session} gate={gate("passed")} />);
    const path = screen.getByText(/운영 경로:/);
    expect(path).toHaveAttribute("data-path", "apk_udp");
    expect(path).toHaveAttribute("data-fallback", "false");
  });
});
