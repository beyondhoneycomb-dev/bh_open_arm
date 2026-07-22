// WP-G-S09 screen composition: it mounts under the /sim route via the plugin seam,
// renders every panel that carries a CG-G-S09 gate, and swaps the sim<->real target
// as a pure state change (no reconnect — proven separately by staticChecks).

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SimScreen from "./screen";
import { resolveScreen } from "../../routes/screenResolver";

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(() => null);
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("SimScreen (WP-G-S09)", () => {
  it("is discovered by the screen resolver at /sim's S-09 id", () => {
    expect(resolveScreen("S-09")).not.toBeNull();
  });

  it("renders the route id and every gated panel", async () => {
    render(<SimScreen />);
    expect(await screen.findByRole("heading", { name: "시뮬레이션", level: 1 })).toBeInTheDocument();
    expect(screen.getByText("/sim")).toBeInTheDocument();

    for (const title of [
      "백엔드 Robot",
      "게인 패리티",
      "시뮬레이션 자산",
      "드라이런 6검사",
      "sim vs real 고스트 오버레이",
    ]) {
      expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
    }
  });

  it("swaps the control target as a pure state change", async () => {
    render(<SimScreen />);
    await screen.findByRole("heading", { name: "시뮬레이션", level: 1 });

    const swap = screen.getByRole("button", { name: /대상 스왑/ });
    expect(swap).toHaveTextContent("→ 실기 (Robot=BiOpenArmFollower)");

    fireEvent.click(swap);
    expect(screen.getByRole("button", { name: /대상 스왑/ })).toHaveTextContent(
      "→ 시뮬 (Robot=BiOpenArmMujoco)",
    );
  });
});
