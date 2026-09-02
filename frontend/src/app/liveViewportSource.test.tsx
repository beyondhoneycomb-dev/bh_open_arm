// The /viewport route against a live channel.
//
// What this pins is the half that works with no model loaded: the stale badge and the control
// block it drives. Before this wiring `latestFrame` was permanently null, so the viewport read
// stale forever and the badge said nothing about the stream. It now says what the stream is
// doing — and still says stale when nothing is arriving, which is the state that must not
// quietly become "fine".

import { act, render, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RealtimeProvider } from "./RealtimeContext";
import { ViewportRoute } from "./ViewportRoute";
import { useLiveViewportSource } from "./liveViewportSource";
import { defaultViewportSource } from "../viewport";
import type { DecodedTextFrame } from "../ws/types";
import type { ReactNode } from "react";

function jointRows(): Record<string, unknown>[] {
  return defaultViewportSource().expectedJointNames.map((name, index) => ({
    name,
    motor: `motor_${index}`,
    position_deg: index,
    position_rad: index / 100,
    velocity_deg_s: 0,
    velocity_rad_s: 0,
    torque_nm: 0,
    limit_lower_deg: -75,
    limit_upper_deg: 75,
    limit_lower_rad: -1.3,
    limit_upper_rad: 1.3,
    near_limit: false,
    blocked_direction: "none",
  }));
}

function telemetryFrame(): DecodedTextFrame {
  return {
    payload: "text",
    frameType: "telemetry",
    body: {
      sequence: 4,
      observation: { "observation.state": [] },
      motor_states: [],
      arms: {},
      joints: jointRows(),
    },
  };
}

function harness() {
  let push: ((frame: DecodedTextFrame) => void) | null = null;
  function wrapper({ children }: { children: ReactNode }) {
    return (
      <RealtimeProvider
        createClient={(hooks) => {
          push = hooks.onTelemetry;
          return { start: () => {}, dispose: () => {} };
        }}
      >
        {children}
      </RealtimeProvider>
    );
  }
  return { wrapper, send: (frame: DecodedTextFrame) => act(() => push?.(frame)) };
}

describe("the viewport's live source", () => {
  it("has no frame before one arrives, which reads as maximally stale", () => {
    const { wrapper } = harness();
    const { result } = renderHook(() => useLiveViewportSource(), { wrapper });

    expect(result.current.latestFrame).toBeNull();
  });

  it("carries the model's joints in the backend's radians once a frame arrives", () => {
    const { wrapper, send } = harness();
    const { result } = renderHook(() => useLiveViewportSource(), { wrapper });

    send(telemetryFrame());

    const frame = result.current.latestFrame;
    expect(frame).not.toBeNull();
    expect(Object.keys(frame!.positionsRad)).toEqual([
      ...defaultViewportSource().expectedJointNames,
    ]);
    expect(frame!.positionsRad["openarm_left_joint1"]).toBe(0);
  });

  it("stamps the frame with its arrival, not with the render that read it", () => {
    // An age measured from render time measures the browser, and a viewport that re-rendered
    // for any reason would report a dead stream as fresh.
    const { wrapper, send } = harness();
    const { result, rerender } = renderHook(() => useLiveViewportSource(), { wrapper });
    send(telemetryFrame());
    const stamped = result.current.latestFrame!.frameMonoMs;

    rerender();

    expect(result.current.latestFrame!.frameMonoMs).toBe(stamped);
  });

  it("leaves the asset alone, because nothing serves a URDF", () => {
    // `openarm_description` is not in this repository. Claiming a loaded model would put a
    // provenance banner over geometry that does not exist.
    const { wrapper } = harness();
    const { result } = renderHook(() => useLiveViewportSource(), { wrapper });

    expect(result.current.robotHandle).toBeNull();
    expect(result.current.assetProvenance).toEqual(defaultViewportSource().assetProvenance);
  });
});

describe("the /viewport route", () => {
  it("renders the panel over the live source", () => {
    const { wrapper: Wrapper } = harness();
    const { container } = render(
      <Wrapper>
        <ViewportRoute />
      </Wrapper>,
    );

    expect(container.textContent).toContain("뷰포트");
  });
});
