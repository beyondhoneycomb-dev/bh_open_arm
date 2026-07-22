// Shell smoke test: the router mounts registry routes under the layout, an
// unimplemented screen renders its placeholder scaffold (no sibling registered,
// so the discovery resolver is empty), the domain-spec query is reachable from
// the screen, /viewport resolves, and an unknown path 404s. The config provider
// loads over an injected fetch — no real backend, no localStorage.

import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AppRoutes } from "./AppRoutes";
import { ConfigProvider } from "./ConfigContext";

function okConfigFetch(): typeof fetch {
  return vi.fn(async () =>
    new Response(
      JSON.stringify({
        layout: { sidebarCollapsed: false, density: "comfortable" },
        theme: { mode: "system" },
        presets: { viewPresets: {} },
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ),
  ) as unknown as typeof fetch;
}

function renderAt(path: string) {
  return render(
    <ConfigProvider fetchImpl={okConfigFetch()}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </ConfigProvider>,
  );
}

describe("app shell", () => {
  it("renders the nav rail with every screen link", async () => {
    renderAt("/");
    expect(await screen.findByRole("navigation", { name: "주 메뉴" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "모터 설정" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "3D 뷰포트" })).toBeInTheDocument();
  });

  it("renders a placeholder scaffold and the domain-spec query for an unimplemented screen", async () => {
    renderAt("/motors");
    expect(await screen.findByRole("heading", { name: "모터 설정" })).toBeInTheDocument();
    expect(screen.getByText(/not yet implemented/)).toBeInTheDocument();
    const specLink = screen.getByRole("link", { name: /MOT · 03/ });
    expect(specLink).toHaveAttribute("href", "/api/spec/03");
  });

  it("serves both S-02 routes with the same screen", async () => {
    renderAt("/home-zero");
    expect(await screen.findByRole("heading", { name: "로봇 연결" })).toBeInTheDocument();
  });

  it("resolves the standalone /viewport route", async () => {
    renderAt("/viewport");
    expect(await screen.findByRole("heading", { name: "3D 뷰포트" })).toBeInTheDocument();
  });

  it("404s an unknown path without inventing a screen", async () => {
    renderAt("/does-not-exist");
    expect(await screen.findByRole("heading", { name: /404/ })).toBeInTheDocument();
  });
});
