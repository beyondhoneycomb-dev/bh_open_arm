// The /viewport route content wires the gate results to the DOM: the block banner
// (CG-G-02b), the stale control gate (CG-G-02e), the collision-mode gap
// (CG-G-02g), the resolved publish rate (CG-G-02i), and the removed point-cloud
// layer (WP-G-02 negative branch). Rendered against fixtures; no backend.

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ViewportPanel } from "./ViewportPanel";
import { defaultViewportSource, type ViewportSource } from "./viewportSource";

// The embedded canvas takes the WebGL-absent (fallback) branch in jsdom; stub
// getContext to null so that is deterministic and quiet.
beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(() => null);
});
afterEach(() => {
  vi.restoreAllMocks();
});

function fullFrameSource(overrides: Partial<ViewportSource> = {}): ViewportSource {
  const base = defaultViewportSource();
  const positionsRad = Object.fromEntries(base.expectedJointNames.map((name) => [name, 0]));
  return { ...base, latestFrame: { positionsRad, frameMonoMs: 1000 }, nowMonoMs: 1100, ...overrides };
}

describe("ViewportPanel", () => {
  it("renders the offline default: provenance, stale control gate, 30 Hz, reduction notice", async () => {
    render(<ViewportPanel />);
    expect(await screen.findByRole("heading", { name: "3D 뷰포트" })).toBeInTheDocument();

    // Provenance is shown (the current v2 asset is not blocked).
    expect(screen.getByText("robot_version")).toBeInTheDocument();
    expect(screen.queryByText(/자산 로드 차단/)).not.toBeInTheDocument();

    // No frames yet -> stale -> control blocked.
    expect(screen.getByText(/제어 입력: 차단 · STALE/)).toBeInTheDocument();

    // Publish rate defaults to 30 Hz; the point-cloud reduction is stated standing.
    expect(screen.getByText("발행율: 30 Hz")).toBeInTheDocument();
    expect(screen.getByText(/포인트클라우드 레이어 없음/)).toBeInTheDocument();

    // Exactly the four layers — no point-cloud toggle.
    expect(screen.getAllByRole("checkbox")).toHaveLength(4);
  });

  it("shows the block banner and cause for a v1 asset (CG-G-02b)", async () => {
    const source = fullFrameSource({
      assetProvenance: {
        source_repo: "openarm_description",
        commit_sha: "0000000000000000000000000000000000000001",
        robot_version: "1.0",
      },
    });
    render(<ViewportPanel source={source} />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("자산 로드 차단");
    expect(alert).toHaveTextContent("1.0");
    expect(alert).toHaveTextContent("2.0");
  });

  it("allows control input when a fresh full-joint frame is present (CG-G-02e recovery)", async () => {
    render(<ViewportPanel source={fullFrameSource()} />);
    expect(await screen.findByText("제어 입력: 허용")).toBeInTheDocument();
  });

  it("surfaces the link7 collision gap only in Collision mode (CG-G-02g)", async () => {
    render(<ViewportPanel source={fullFrameSource()} />);
    await screen.findByRole("heading", { name: "3D 뷰포트" });

    // Auto mode: no gap alert.
    expect(screen.queryByText(/collisions.yaml 미선언/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: "Collision" }));

    const gap = screen.getByText(/collisions.yaml 미선언/);
    expect(gap).toHaveTextContent("openarm_left_link7");
    expect(gap).toHaveTextContent("openarm_right_link7");
  });

  it("rejects an over-cap publish rate rather than clamping (CG-G-02i)", async () => {
    render(<ViewportPanel source={fullFrameSource({ requestedPublishRateHz: 90 })} />);
    expect(await screen.findByText(/발행율 설정 거부/)).toBeInTheDocument();
  });
});
