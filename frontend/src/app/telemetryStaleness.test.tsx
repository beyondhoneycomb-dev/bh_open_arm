// The badge and the notice against a board that stopped advancing.
//
// This is the failure the field exists for, and it has happened: a CAN adapter left the bus, the
// tick that fills the boards raised and returned, and the push loop kept sending the last reading
// at the full rate. Frames arrived for forty-five minutes and every one of them was a real
// measurement of a moment three quarters of an hour earlier.
//
// So the assertion is not that the badge reads a field. It is that a frame which is arriving,
// well-formed, and full of plausible numbers still reports a disconnected arm — because the one
// thing separating it from a live one is the server's verdict on its age.

import { MemoryRouter } from "react-router-dom";
import { act, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AppRoutes } from "./AppRoutes";
import { ConfigProvider } from "./ConfigContext";
import { RealtimeProvider } from "./RealtimeContext";
import type { DecodedTextFrame } from "../ws/types";

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

// One arm's liveness as `backend/ws/telemetry.py` writes it. Every guard field reads healthy, so
// `stale` is the only thing the two frames below disagree about.
function armEntry(stale: boolean, readAgeS: number) {
  return {
    read_age_s: readAgeS,
    stale,
    tick_index: 41,
    observation_present: true,
    bus_read_ok: true,
    lock_acquired: true,
    residual_exceeded: false,
  };
}

function telemetryFrame(stale: boolean, readAgeS: number): DecodedTextFrame {
  return {
    payload: "text",
    frameType: "telemetry",
    body: {
      sequence: 41,
      observation: { "observation.state": [1.0, 2.0, 3.0] },
      motor_states: [],
      arms: { left: armEntry(stale, readAgeS), right: armEntry(stale, readAgeS) },
    },
  };
}

function renderShell() {
  let push: ((frame: DecodedTextFrame) => void) | null = null;
  const view = render(
    <ConfigProvider fetchImpl={okConfigFetch()}>
      <RealtimeProvider
        createClient={(hooks) => {
          push = hooks.onTelemetry;
          return { start: () => {}, dispose: () => {} };
        }}
      >
        <MemoryRouter initialEntries={["/"]}>
          <AppRoutes />
        </MemoryRouter>
      </RealtimeProvider>
    </ConfigProvider>,
  );
  return {
    container: view.container,
    send: (frame: DecodedTextFrame) => act(() => push?.(frame)),
  };
}

describe("a reading that stopped advancing is not a connected arm", () => {
  it("reports connected while the server says the reading is fresh", () => {
    const { container, send } = renderShell();

    send(telemetryFrame(false, 0.004));

    expect(container.querySelector('[data-badge="connection"]')).toHaveTextContent("연결됨");
    expect(container.querySelector('[data-arm-reading="stopped"]')).toBeNull();
  });

  it("reports disconnected once every arm is stale, though frames keep arriving", () => {
    const { container, send } = renderShell();
    send(telemetryFrame(false, 0.004));
    expect(container.querySelector('[data-badge="connection"]')).toHaveTextContent("연결됨");

    send(telemetryFrame(true, 2700.0));

    expect(container.querySelector('[data-badge="connection"]')).toHaveTextContent("끊김");
  });

  it("says the reading stopped, rather than leaving it as a session that never started", () => {
    // The badge alone cannot separate the two, and they want opposite things from the operator:
    // one is a session not opened, the other is a rig to go and look at.
    const { container, send } = renderShell();

    send(telemetryFrame(true, 2700.0));

    const notice = container.querySelector('[data-arm-reading="stopped"]');
    expect(notice).not.toBeNull();
    expect(notice).toHaveAttribute("role", "alert");
    expect(notice).toHaveTextContent(/멈췄습니다/);
  });

  it("keeps reporting connected while one arm is still advancing", () => {
    // One side's reader can stop without the other's. Reporting the whole rig disconnected would
    // hide that the live half is still moving.
    const { container, send } = renderShell();

    send({
      payload: "text",
      frameType: "telemetry",
      body: {
        sequence: 41,
        observation: { "observation.state": [1.0] },
        motor_states: [],
        arms: { left: armEntry(true, 2700.0), right: armEntry(false, 0.004) },
      },
    });

    expect(container.querySelector('[data-badge="connection"]')).toHaveTextContent("연결됨");
    expect(container.querySelector('[data-arm-reading="stopped"]')).toBeNull();
  });
});
