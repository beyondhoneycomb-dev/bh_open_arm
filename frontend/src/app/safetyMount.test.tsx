// The shell half of CG-G-03b. estopReachability.test.tsx proves GlobalSafetyBar renders a
// pressable stop when given props; this proves the shell hands it those props on every
// route the router serves, including the viewport route and an unknown path that 404s.
// Without this, the component could satisfy its own matrix while no screen mounted it.
//
// It also pins the failure branch: with no backend link, pressing the stop must tell the
// operator it did not land (NORM-007 — a stop believed to have worked is the hazard).

import { MemoryRouter } from "react-router-dom";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { allRoutePaths } from "../routes/registry";
import { AppRoutes } from "./AppRoutes";
import { ConfigProvider } from "./ConfigContext";
import { RealtimeProvider } from "./RealtimeContext";
import { STOP_HOLD_SENDER } from "./backendLink";

const UNKNOWN_PATH = "/no-such-route";

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

// The shell reads the realtime client for the lease surface, so rendering it needs a provider.
// This double never connects: it satisfies the lifetime and reports no lease, which is what a
// page that has not been granted control looks like.
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

describe("the shell mounts the stop surface on every route", () => {
  it("offers a pressable STOP_HOLD control on all 14 routes and on an unknown path", () => {
    const paths = [...allRoutePaths(), UNKNOWN_PATH];
    const missing: string[] = [];
    const disabled: string[] = [];

    for (const path of paths) {
      const { unmount } = renderAt(path);
      const stop = screen.queryByRole("button", {
        name: /소프트 스톱/,
      }) as HTMLButtonElement | null;
      if (!stop) {
        missing.push(path);
      } else if (stop.disabled) {
        disabled.push(path);
      }
      unmount();
    }

    expect({ missing, disabled }).toEqual({ missing: [], disabled: [] });
  });

  it("keeps the physical-E-Stop guidance beside it, and adds no second stop button", () => {
    const { container } = renderAt("/manual");
    expect(container.querySelector(".oa-stop--hard")).not.toBeNull();
    const stopGroup = container.querySelector(".oa-stops");
    expect(stopGroup).not.toBeNull();
    expect(within(stopGroup as HTMLElement).getAllByRole("button")).toHaveLength(1);
  });
});

describe("a stop that cannot be delivered says so (NORM-007)", () => {
  // The wiring seam. While it is null the shell has no path to the robot, and the operator
  // must be told that before reaching for the button, not only after pressing it.
  it("warns that the stop has no delivery path while no sender is wired", () => {
    expect(STOP_HOLD_SENDER).toBeNull();
    const { container } = renderAt("/");
    expect(container.querySelector('[data-stop-link="absent"]')).not.toBeNull();
  });

  it("reports the failure prominently when the stop is pressed with no link", () => {
    const { container } = renderAt("/");
    expect(container.querySelector('[data-stop-delivery="failed"]')).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /소프트 스톱/ }));

    const failure = container.querySelector('[data-stop-delivery="failed"]');
    expect(failure).not.toBeNull();
    // role=alert so a screen reader interrupts rather than waiting to be asked.
    expect(failure).toHaveAttribute("role", "alert");
    expect(failure).toHaveTextContent(/전달되지 않았습니다/);
  });

  it("does not redraw the unread flag as applied when the toggle cannot be written", () => {
    const { container } = renderAt("/");
    const toggle = screen.getByRole("checkbox", { name: /커플드/ }) as HTMLInputElement;
    expect(toggle.checked).toBe(false);

    fireEvent.click(toggle);

    expect(container.querySelector('[data-flag-write="failed"]')).not.toBeNull();
    // Still unread: the click reached no writer, so nothing about the flag changed.
    expect(container.querySelector('[data-flag="use_velocity_and_torque"]')).toHaveAttribute(
      "data-flag-value",
      "unknown",
    );
  });
});

describe("no badge claims a state the shell never observed", () => {
  it("reports disconnected, and no mode, profile, control holder or CAN interface", () => {
    const { container } = renderAt("/");
    expect(container.querySelector('[data-badge="connection"]')).toHaveTextContent("끊김");
    expect(container.querySelector('[data-badge="mode"]')).toHaveTextContent("미상");
    expect(container.querySelector('[data-badge="profile"]')).toHaveTextContent("미로드");
    expect(container.querySelector('[data-badge="control-holder"]')).toHaveTextContent("없음");
    expect(container.querySelector('[data-badge="can-unobserved"]')).not.toBeNull();
  });

  it("renders no nominal badge anywhere — nominal is a claim, and nothing was observed", () => {
    const { container } = renderAt("/");
    const bar = container.querySelector(".oa-safety-bar");
    expect(bar).not.toBeNull();
    expect((bar as HTMLElement).querySelectorAll(".oa-badge--nominal")).toHaveLength(0);
  });

  it("shows no dummy-mode banner, since no dummy backend is running either", () => {
    const { container } = renderAt("/");
    expect(container.querySelector(".oa-dummy-banner")).toBeNull();
  });
});
