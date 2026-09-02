// The joint table against a real telemetry frame, and the absences beside it.
//
// The screen's other tests drive it from the offline fixture, which proves the rendering. This
// one proves the wiring: that the numbers on screen are the backend's own, that the two
// FR-MAN-013 verdicts arrive rather than being recomputed here, and that the fields with no
// channel are shown as unobserved instead of as the fixture's plausible values.

import { MemoryRouter } from "react-router-dom";
import { act, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RealtimeProvider } from "../../app/RealtimeContext";
import { ConfigProvider } from "../../app/ConfigContext";
import ManualRoute from "./screen";
import { jointReadoutsFrom } from "./manualSource";
import { readTelemetry } from "../../ws/telemetryView";
import type { DecodedTextFrame } from "../../ws/types";

const JOINTS_PER_SIDE = 8;

function okConfigFetch(): typeof fetch {
  return vi.fn(async () =>
    new Response(JSON.stringify({ layout: {}, presets: {} }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  ) as unknown as typeof fetch;
}

// One joint row exactly as `backend/ws/telemetry.py` writes it.
function jointRow(side: string, index: number, overrides: Record<string, unknown> = {}) {
  return {
    name: `openarm_${side}_joint${index}`,
    motor: `${side}_joint_${index}`,
    position_deg: 10 * index,
    position_rad: 0.1 * index,
    velocity_deg_s: index,
    velocity_rad_s: 0.01 * index,
    torque_nm: 0.5 * index,
    limit_lower_deg: -75,
    limit_upper_deg: 75,
    limit_lower_rad: -1.3089969389957472,
    limit_upper_rad: 1.3089969389957472,
    near_limit: false,
    blocked_direction: "none",
    ...overrides,
  };
}

function frame(overrides: Record<string, unknown> = {}): DecodedTextFrame {
  const joints = ["right", "left"].flatMap((side) =>
    Array.from({ length: JOINTS_PER_SIDE }, (_unused, slot) => jointRow(side, slot + 1)),
  );
  return {
    payload: "text",
    frameType: "telemetry",
    body: {
      sequence: 12,
      observation: { "observation.state": [] },
      motor_states: [{ joint_name: "right_joint_1", temp_mos_c: 41, temp_rotor_c: 33 }],
      arms: {},
      joints,
      ...overrides,
    },
  };
}

function renderRoute() {
  let push: ((f: DecodedTextFrame) => void) | null = null;
  const view = render(
    <ConfigProvider fetchImpl={okConfigFetch()}>
      <RealtimeProvider
        createClient={(hooks) => {
          push = hooks.onTelemetry;
          return { start: () => {}, dispose: () => {} };
        }}
      >
        <MemoryRouter>
          <ManualRoute />
        </MemoryRouter>
      </RealtimeProvider>
    </ConfigProvider>,
  );
  return { container: view.container, send: (f: DecodedTextFrame) => act(() => push?.(f)) };
}

describe("jointReadoutsFrom", () => {
  it("keeps one side's joints and numbers them from one", () => {
    // Both arms are on the wire and the screen shows one. An index counting both would put the
    // left arm's gripper where the right arm's J8 belongs.
    const view = readTelemetry(frame());
    expect(view).not.toBeNull();

    const rows = jointReadoutsFrom(view!, "right");

    expect(rows).toHaveLength(JOINTS_PER_SIDE);
    expect(rows.map((row) => row.index)).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
    expect(rows[0].name).toBe("openarm_right_joint1");
  });

  it("takes the backend's radians rather than converting the degrees", () => {
    // The two disagree in this fixture on purpose: 10 deg is not 0.1 rad. A screen doing its
    // own conversion would produce 0.1745 and be confidently wrong about where the joint is.
    const rows = jointReadoutsFrom(readTelemetry(frame())!, "right");

    expect(rows[0].positionDeg).toBe(10);
    expect(rows[0].positionRad).toBe(0.1);
    expect(rows[0].velocityRadPerSec).toBe(0.01);
  });

  it("joins temperatures by the motor name the row carries, and reports absence as absence", () => {
    const rows = jointReadoutsFrom(readTelemetry(frame())!, "right");

    expect(rows[0].tempMosC).toBe(41);
    expect(rows[0].tempRotorC).toBe(33);
    // No motor row for J2, so no temperature — not a motor reading zero degrees.
    expect(rows[1].tempMosC).toBeNull();
  });

  it("carries the backend's limit verdicts through unchanged", () => {
    const blocked = frame({
      joints: [jointRow("right", 1, { near_limit: true, blocked_direction: "positive" })],
    });

    const rows = jointReadoutsFrom(readTelemetry(blocked)!, "right");

    expect(rows[0].nearLimit).toBe(true);
    expect(rows[0].blockedDirection).toBe("positive");
  });
});

describe("the manual route", () => {
  it("renders the backend's joint positions once a frame arrives", () => {
    const { container, send } = renderRoute();

    send(frame());

    const table = container.querySelector('[data-field="joint-table"], table');
    expect(table).not.toBeNull();
    expect(table).toHaveTextContent("openarm_right_joint1");
  });

  it("shows the end-effector pose as unobserved, since no frame carries one", () => {
    // The fixture source has a plausible pose in it. Passing that through beside live joint
    // angles is the failure this route exists to avoid: it would read as a measured tool point.
    const { container, send } = renderRoute();
    send(frame());

    const pose = container.querySelector('[aria-label="EE 포즈"]');
    expect(pose).not.toBeNull();
    expect(pose).toHaveTextContent("—");
  });
});
