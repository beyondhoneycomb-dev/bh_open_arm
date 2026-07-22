// WP-G-S05 screen composition: it mounts under /teleop via the plugin seam and
// renders every panel that carries a CG-G-S05 gate. The viewport canvas has no 2D
// context under jsdom, so getContext is stubbed exactly as the sibling S-09 test does.

import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import TeleopScreen from "./screen";
import { resolveScreen } from "../../routes/screenResolver";

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(() => null);
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("TeleopScreen (WP-G-S05)", () => {
  it("is discovered by the screen resolver at /teleop's S-05 id", () => {
    expect(resolveScreen("S-05")).not.toBeNull();
  });

  it("renders the route id and every gated panel", () => {
    render(<TeleopScreen />);
    expect(screen.getByRole("heading", { name: "텔레옵", level: 1 })).toBeInTheDocument();
    expect(screen.getByText("/teleop")).toBeInTheDocument();

    for (const label of [
      "명령 소스 배타성",
      "VR 세션",
      "정렬 상태머신",
      "클러치 상태",
      "링크 워치독",
      "C-Lat 제어채널 지연",
      "One-Euro 스무더 파라미터",
      "스케일 (위치·회전 분리)",
      "WebXR 진입점",
      "리더 vs 팔로워 3D",
    ]) {
      expect(screen.getByRole("region", { name: label })).toBeInTheDocument();
    }
  });
});
