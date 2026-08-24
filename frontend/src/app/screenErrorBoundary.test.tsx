// The blast radius of a screen that throws. Both cases here are about what SURVIVES, not
// about the panel that replaces the screen: a chunk that fails to load must cost the
// operator that one screen, never the stop control (CG-G-03b) and never the nav rail that
// is the way back.
//
// The throw is injected through the screen-resolver seam rather than by breaking a real
// screen, because the fault being modelled is a load failure of ANY screen chunk — a bundle
// hash that moved under an open tab — and no single screen owns that.

import { MemoryRouter } from "react-router-dom";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const THROWING_SCREEN_ID = "S-04";
const HEALTHY_SCREEN_ID = "S-01";
const CHUNK_ERROR = "Failed to fetch dynamically imported module: /assets/S-04-a1b2c3.js";

vi.mock("../routes/screenResolver", () => ({
  resolveScreen: (id: string) => {
    if (id === THROWING_SCREEN_ID) {
      return function BrokenScreen(): never {
        throw new Error(CHUNK_ERROR);
      };
    }
    return null;
  },
  registeredScreenIds: () => [THROWING_SCREEN_ID],
}));

const { AppRoutes } = await import("./AppRoutes");
const { ConfigProvider } = await import("./ConfigContext");
const { RealtimeProvider } = await import("./RealtimeContext");
const { screenById } = await import("../routes/registry");

function okConfigFetch(): typeof fetch {
  return vi.fn(async () =>
    new Response(
      JSON.stringify({
        layout: { sidebarCollapsed: false, density: "comfortable" },
        presets: { viewPresets: {} },
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ),
  ) as unknown as typeof fetch;
}

function stubRealtimeClient() {
  return { start: () => {}, dispose: () => {} };
}

function renderAt(path: string) {
  return render(
    <ConfigProvider fetchImpl={okConfigFetch()}>
      <RealtimeProvider createClient={() => stubRealtimeClient()}>
        <MemoryRouter initialEntries={[path]}>
          <AppRoutes />
        </MemoryRouter>
      </RealtimeProvider>
    </ConfigProvider>,
  );
}

// React prints the caught error and its component stack; both are expected output here and
// would otherwise bury the run's real failures.
let consoleError: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  consoleError.mockRestore();
});

const brokenPath = screenById(THROWING_SCREEN_ID).paths[0];

describe("a screen that throws costs one panel, not the page", () => {
  it("keeps the stop control pressable while the screen is replaced by its error", () => {
    const { container } = renderAt(brokenPath);

    const stop = screen.getByRole("button", { name: /소프트 스톱/ }) as HTMLButtonElement;
    expect(stop.disabled).toBe(false);
    expect(container.querySelector(".oa-safety-bar")).not.toBeNull();
    expect(screen.getByRole("alert", { name: /표시하지 못했습니다/ })).not.toBeNull();
  });

  it("names the failure instead of showing a blank panel", () => {
    const { container } = renderAt(brokenPath);
    expect(container.querySelector(".oa-screen-error__detail")).toHaveTextContent(CHUNK_ERROR);
  });

  it("keeps the nav rail, which is the recovery path it offers instead of a reload", () => {
    renderAt(brokenPath);
    expect(screen.getByRole("navigation", { name: "주 메뉴" })).not.toBeNull();
    // No reload control: a reload ends the WS session, which drops the lease and latches.
    expect(screen.queryByRole("button", { name: /다시|새로고침|reload/i })).toBeNull();
  });

  it("renders the next route after a failure — the boundary resets on the path", () => {
    renderAt(brokenPath);
    expect(screen.getByRole("alert", { name: /표시하지 못했습니다/ })).not.toBeNull();

    fireEvent.click(screen.getByRole("link", { name: screenById(HEALTHY_SCREEN_ID).title }));

    expect(screen.queryByRole("alert", { name: /표시하지 못했습니다/ })).toBeNull();
    expect(screen.getByRole("heading", { name: screenById(HEALTHY_SCREEN_ID).title })).not.toBeNull();
  });
});
