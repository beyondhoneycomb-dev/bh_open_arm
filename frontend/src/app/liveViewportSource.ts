// The viewport's input bundle, built from the realtime channel.
//
// Its own module rather than a second export off the route, because both the standalone
// /viewport route and the screens that embed the viewport read it. Two builders over one frame
// is how an embed and a route drift into two viewports, which is what WP-G-02's public surface
// exists to prevent.

import { useMemo } from "react";

import { defaultViewportSource, jointFrameFor, type ViewportSource } from "../viewport";
import { useRealtime } from "./RealtimeContext";

// Build the viewport's input bundle from the realtime channel.
//
// `nowMonoMs` is read at build time rather than held in state: the age it feeds is compared
// against the arrival of the last frame, and a `now` that only moved when a frame arrived would
// report a stream that died as permanently fresh.
export function useLiveViewportSource(): ViewportSource {
  const { telemetry, telemetryAtMs } = useRealtime();
  const offline = defaultViewportSource();
  return useMemo(
    () => ({
      ...offline,
      latestFrame:
        telemetry === null || telemetryAtMs === null
          ? null
          : jointFrameFor(telemetry.joints, offline.expectedJointNames, telemetryAtMs),
      nowMonoMs: performance.now(),
    }),
    // The frame identity is what changes per tick; the offline half is rebuilt identically
    // every render and is not a reason to recompute.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [telemetry, telemetryAtMs],
  );
}
