// WP-G-S01 dashboard render tests — the gates a static scan cannot prove. The
// dashboard aggregates and renders; these assert every FR-GUI-100 item is present,
// the nine §4.3 subsystems render in all four states, a not-landed source renders
// UNAVAILABLE (never OK), the camera tile count follows the active-stream array,
// the cycle-time reads UNAVAILABLE here (PG-RT-001b hardware-deferred) with the
// WARN cause split or explicit-unimplemented when a landed WARN is injected, the
// coupled data flags and intruder status are shown, and the CRITICAL-only area
// leads with the backend-flagged rows.

import { render as renderTree, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ReactElement, ReactNode } from "react";

import DashboardScreen from "./screen";
import { ConfigProvider } from "../../app/ConfigContext";
import { resolveScreen } from "../../routes/screenResolver";
import { defaultDashboardData } from "./dashboardSource";
import { CANONICAL_SUBSYSTEM_IDS } from "./types";
import type {
  CameraStreamStat,
  DashboardData,
  DashboardSource,
  DiagnosticState,
  SubsystemStatus,
} from "./types";

// The end-effector control reads the shared runtime config, which the app supplies
// at its root, so these renders supply it too. The injected fetch keeps the config
// load off the network; the tool registry is EndEffectorPanel.test's subject and is
// left unserved here.
function configFetch(): typeof fetch {
  return vi.fn(
    async () =>
      new Response(
        JSON.stringify({
          layout: { sidebarCollapsed: false, density: "comfortable" },
          presets: { viewPresets: {} },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
  ) as unknown as typeof fetch;
}

function ConfigWrapper({ children }: { children: ReactNode }) {
  return <ConfigProvider fetchImpl={configFetch()}>{children}</ConfigProvider>;
}

// Wrapped through the `wrapper` option so a rerender keeps the provider.
function render(ui: ReactElement) {
  return renderTree(ui, { wrapper: ConfigWrapper });
}

function sourceWith(overrides: Partial<DashboardData>): DashboardSource {
  const base = defaultDashboardData();
  return { load: () => ({ ...base, ...overrides }) };
}

// The nine canonical subsystems, each set to one supplied state (or null).
function subsystemsInStates(
  states: readonly (DiagnosticState | null)[],
  critical: ReadonlySet<string> = new Set(),
): SubsystemStatus[] {
  return CANONICAL_SUBSYSTEM_IDS.map((id, index) => ({
    id,
    label: id,
    status: states[index % states.length],
    detail: `${id} detail`,
    critical: critical.has(id),
  }));
}

describe("DashboardScreen (WP-G-S01)", () => {
  it("is discovered by the screen resolver at /'s S-01 id", () => {
    expect(resolveScreen("S-01")).not.toBeNull();
  });

  it("renders the route id and title", () => {
    render(<DashboardScreen />);
    expect(screen.getByRole("heading", { name: "대시보드", level: 1 })).toBeInTheDocument();
    expect(screen.getByText("/")).toBeInTheDocument();
  });

  it("shows every FR-GUI-100 item (CG-G-S01b)", () => {
    render(<DashboardScreen />);
    for (const testid of [
      "fr100-connection",
      "fr100-can-lock",
      "fr100-velocity-torque",
      "fr100-push-to-hub",
      "fr100-cameras",
      "fr100-disk",
      "fr100-gpu",
      "fr100-cycle-p95",
      "fr100-sessions",
      "fr100-unacked",
    ]) {
      expect(screen.getByTestId(testid)).toBeInTheDocument();
    }
    // Disk free + projected exhaustion, GPU/VRAM, unacked count are the composite
    // items — assert their sub-parts too.
    expect(screen.getByTestId("disk-exhaustion")).toBeInTheDocument();
    expect(screen.getByTestId("gpu-vram")).toBeInTheDocument();
    expect(screen.getByTestId("unacked-count")).toHaveTextContent("2");
  });

  it("renders all nine §4.3 subsystems (CG-5-02a)", () => {
    render(<DashboardScreen source={sourceWith({ subsystems: subsystemsInStates(["OK"]) })} />);
    for (const id of CANONICAL_SUBSYSTEM_IDS) {
      expect(screen.getByTestId(`subsystem-${id}`)).toBeInTheDocument();
    }
    // Exactly nine rows — no invented row, none dropped.
    const grid = screen.getByTestId("subsystem-grid");
    expect(within(grid).getAllByRole("listitem").length).toBe(CANONICAL_SUBSYSTEM_IDS.length);
  });

  it("renders each subsystem in all four diagnostic states (CG-5-02a)", () => {
    render(
      <DashboardScreen
        source={sourceWith({ subsystems: subsystemsInStates(["OK", "WARN", "ERROR", "STALE"]) })}
      />,
    );
    const seen = new Set<string>();
    for (const id of CANONICAL_SUBSYSTEM_IDS) {
      const row = screen.getByTestId(`subsystem-${id}`);
      seen.add(row.getAttribute("data-render-state") ?? "");
    }
    for (const state of ["OK", "WARN", "ERROR", "STALE"]) {
      expect(seen.has(state)).toBe(true);
    }
  });

  it("renders a not-landed subsystem as UNAVAILABLE, never OK (CG-G-S01e)", () => {
    render(
      <DashboardScreen
        source={sourceWith({
          subsystems: subsystemsInStates([null]),
        })}
      />,
    );
    const row = screen.getByTestId("subsystem-vr_link");
    expect(row).toHaveAttribute("data-render-state", "UNAVAILABLE");
    expect(row).not.toHaveAttribute("data-render-state", "OK");
    expect(row.className).toContain("oa-dash__state--unavailable");
    expect(row.className).not.toContain("oa-dash__state--ok");
  });

  it("derives the camera tile count from the active-stream array (CG-G-S01c)", () => {
    const three: CameraStreamStat[] = [
      { slot: "left_wrist", uiLabel: "wrist_left", datasetKey: "observation.images.left_wrist", fps: 30, jitterMs: 1, state: "OK" },
      { slot: "right_wrist", uiLabel: "wrist_right", datasetKey: "observation.images.right_wrist", fps: 30, jitterMs: 1, state: "OK" },
      { slot: "ceiling", uiLabel: "ceiling", datasetKey: "observation.images.ceiling", fps: 30, jitterMs: 1, state: "OK" },
    ];
    const { rerender } = render(<DashboardScreen source={sourceWith({ cameras: three })} />);
    expect(screen.getByTestId("fr100-cameras")).toHaveAttribute("data-stream-count", "3");
    expect(screen.getAllByTestId(/^camera-tile-/).length).toBe(3);
    // Both label systems are shown per tile (CG-G-S06b consistency).
    expect(screen.getByTestId("camera-tile-ceiling")).toHaveTextContent("observation.images.ceiling");

    rerender(<DashboardScreen source={sourceWith({ cameras: [] })} />);
    expect(screen.getByTestId("fr100-cameras")).toHaveAttribute("data-stream-count", "0");
    expect(screen.getByTestId("cameras-empty")).toBeInTheDocument();
    expect(screen.queryAllByTestId(/^camera-tile-/).length).toBe(0);
  });

  it("reads the cycle-time p95 as UNAVAILABLE here, sourced from PG-RT-001b (CG-G-S01d/e)", () => {
    render(<DashboardScreen />);
    const tile = screen.getByTestId("fr100-cycle-p95");
    expect(tile).toHaveAttribute("data-render-state", "UNAVAILABLE");
    expect(screen.getByTestId("cycle-unavailable")).toBeInTheDocument();
    expect(screen.getByTestId("cycle-source")).toHaveTextContent("PG-RT-001b");
    // No fabricated number in the unavailable state.
    expect(screen.queryByTestId("cycle-p95")).toBeNull();
  });

  it("shows the four-way cause split on a landed WARN (CG-5-02e)", () => {
    render(
      <DashboardScreen
        source={sourceWith({
          cycleTime: {
            available: true,
            source: "PG-RT-001b",
            p50Ms: 24,
            p95Ms: 38,
            p99Ms: 51,
            targetDisplay: "33.3 ms (30 fps)",
            warn: {
              kind: "cause-breakdown",
              canMs: 2,
              cameraGrabEncodeMs: 6,
              ikMs: 1,
              wsSerializationMs: 3,
              consecutiveCycles: 12,
            },
          },
        })}
      />,
    );
    const breakdown = screen.getByTestId("cycle-cause-breakdown");
    expect(breakdown).toBeInTheDocument();
    for (const part of ["cycle-cause-can", "cycle-cause-camera", "cycle-cause-ik", "cycle-cause-ws"]) {
      expect(screen.getByTestId(part)).toBeInTheDocument();
    }
    expect(screen.getByTestId("cycle-p95")).toHaveTextContent("38");
  });

  it("marks the cause split explicitly unimplemented rather than a silent total (CG-5-02e)", () => {
    render(
      <DashboardScreen
        source={sourceWith({
          cycleTime: {
            available: true,
            source: "PG-RT-001b",
            p50Ms: 24,
            p95Ms: 38,
            p99Ms: 51,
            targetDisplay: "33.3 ms (30 fps)",
            warn: { kind: "unimplemented", note: "계측 훅 미배치" },
          },
        })}
      />,
    );
    expect(screen.getByTestId("cycle-cause-unimplemented")).toBeInTheDocument();
    expect(screen.queryByTestId("cycle-cause-breakdown")).toBeNull();
  });

  it("always shows use_velocity_and_torque and push_to_hub (CG-5-02f)", () => {
    render(<DashboardScreen source={sourceWith({ flags: { useVelocityAndTorque: false, pushToHub: true } })} />);
    expect(screen.getByTestId("fr100-velocity-torque")).toHaveAttribute("data-enabled", "false");
    expect(screen.getByTestId("velocity-torque-warn")).toBeInTheDocument();
    expect(screen.getByTestId("fr100-push-to-hub")).toHaveAttribute("data-enabled", "true");
    expect(screen.getByTestId("push-to-hub-warn")).toBeInTheDocument();
  });

  it("shows the intruder-detection status (CG-5-02g)", () => {
    render(<DashboardScreen />);
    // Default: no intruder.
    expect(screen.getByTestId("intruder-can0")).toHaveAttribute("data-intruder-present", "false");

    render(
      <DashboardScreen
        source={sourceWith({
          can: [
            {
              iface: "can0",
              lockHeld: true,
              boundSocketCount: 2,
              intruderPresent: true,
              intruderPids: [4821],
              state: "ERROR",
            },
          ],
        })}
      />,
    );
    const intruders = screen.getAllByTestId("intruder-can0");
    const withIntruder = intruders.find((node) => node.getAttribute("data-intruder-present") === "true");
    expect(withIntruder).toBeDefined();
    expect(withIntruder).toHaveTextContent("4821");
  });

  it("leads with a CRITICAL-only area, empty by default and populated by the backend flag", () => {
    render(<DashboardScreen source={sourceWith({ subsystems: subsystemsInStates(["OK"]) })} />);
    expect(screen.getByTestId("critical-area")).toHaveAttribute("data-critical-count", "0");
    expect(screen.getByTestId("critical-empty")).toBeInTheDocument();

    render(
      <DashboardScreen
        source={sourceWith({
          subsystems: subsystemsInStates(["STALE"], new Set(["gui_backend"])),
        })}
      />,
    );
    const area = screen.getAllByTestId("critical-area").find(
      (node) => node.getAttribute("data-critical-count") === "1",
    );
    expect(area).toBeDefined();
    expect(within(area as HTMLElement).getByTestId("critical-gui_backend")).toBeInTheDocument();
  });
});
