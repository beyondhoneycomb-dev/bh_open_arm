// The shell half of FR-GUI-080. ModeAuthorityTable.test.tsx proves the table renders the
// eight rows when it is given props; this proves the shell actually renders it, on every
// route the router serves. A component can satisfy its own tests while nothing mounts it,
// and only a test that renders the shell can tell those two apart.
//
// It also pins the honest reading of an unknown mode: with nothing in this build reporting
// one, no row may be marked. A marked row is read as "the rig is in this mode", and IDLE is
// a state the arm can be in, not a stand-in for "we did not look".

import { MemoryRouter } from "react-router-dom";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { allRoutePaths } from "../routes/registry";
import { AppRoutes } from "./AppRoutes";
import { ConfigProvider } from "./ConfigContext";
import { RealtimeProvider } from "./RealtimeContext";

const AUTHORITY_TABLE = "8모드 제어권 표";
const MODE_COUNT = 8;
const SUMMARY_LABEL = "모드별 제어권";

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

// The disclosure is opened before the table is queried, and that is not ceremony. jsdom
// leaves the children of a closed `details` in the tree and visible to queries; a real
// browser renders neither. Querying it closed would keep this file green even if the
// disclosure were broken shut, which is the one failure it exists to catch.
function openAuthority(container: HTMLElement): HTMLDetailsElement {
  const disclosure = container.querySelector("details.oa-authority") as HTMLDetailsElement | null;
  if (disclosure === null) {
    throw new Error("no mode-authority disclosure in the shell");
  }
  fireEvent.click(within(disclosure).getByText(SUMMARY_LABEL));
  return disclosure;
}

describe("the shell mounts the mode-authority reference", () => {
  it("opens to the eight-mode table on every route", () => {
    const missing: string[] = [];

    for (const path of allRoutePaths()) {
      const { container, unmount } = renderAt(path);
      const disclosure = container.querySelector("details.oa-authority");
      if (disclosure === null) {
        missing.push(path);
      } else {
        openAuthority(container);
        const table = screen.getByRole("table", { name: AUTHORITY_TABLE });
        expect(within(table).getAllByRole("row").slice(1)).toHaveLength(MODE_COUNT);
      }
      unmount();
    }

    expect(missing).toEqual([]);
  });

  it("starts collapsed, so the reference costs no screen area until it is asked for", () => {
    const { container } = renderAt("/");
    const disclosure = container.querySelector("details.oa-authority") as HTMLDetailsElement;
    expect(disclosure).not.toBeNull();
    expect(disclosure.open).toBe(false);
  });

  it("marks no mode, because this build observes none", () => {
    const { container } = renderAt("/");
    openAuthority(container);
    const table = screen.getByRole("table", { name: AUTHORITY_TABLE });
    const marked = within(table)
      .getAllByRole("row")
      .filter((row) => row.getAttribute("aria-current") !== null);
    expect(marked).toEqual([]);
  });
});
