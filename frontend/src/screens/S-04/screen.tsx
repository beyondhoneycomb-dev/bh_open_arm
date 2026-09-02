// Route entry for S-04 (/manual), discovered by routes/screenResolver via its import.meta.glob.
// It binds the one channel this screen has — the telemetry frame's joint rows — and renders the
// facade over everything else the offline default already carries.
//
// What is live: the joint table (position in both units, velocity, torque, the soft limits, and
// the two FR-MAN-013 verdicts), the temperatures joined onto it from `motor_states`, and the
// stream age the motion gate reads. Nothing else is: the end-effector pose, the IK parameters,
// the gain profiles, the home profiles and the teach list have no channel on any frame the
// backend sends today.
//
// The pose is the one of those the operator would read as a measurement, so it is passed as
// absent and the panel renders a dash. The rest are configuration shapes — a step vocabulary, a
// solver's damping, a profile's name — which nobody mistakes for a reading of this rig.
//
// One arm at a time, because that is the shape the screen has: `ManualSource.side` names it and
// there is no selector. Both arms are on the wire, so a selector is a screen change and not a
// transport one.

import { useRealtime } from "../../app/RealtimeContext";
import ManualScreen from "./ManualScreen";
import { defaultManualSource, jointReadoutsFrom, type ManualSource } from "./manualSource";

// No pose has been reported. Six nulls rather than a zeroed pose: the origin is a place the
// tool can actually be.
const POSE_UNREPORTED = {
  xMm: null,
  yMm: null,
  zMm: null,
  rollDeg: null,
  pitchDeg: null,
  yawDeg: null,
} as const;

// A stream that has delivered nothing is infinitely old, which is what the age rule needs to
// read to hold the motion gate shut. Zero would be "a frame arrived at time zero".
const NO_FRAME_MONO_MS = Number.NEGATIVE_INFINITY;

export default function ManualRoute() {
  const { telemetry, telemetryAtMs } = useRealtime();
  const offline = defaultManualSource();
  const source: ManualSource = {
    ...offline,
    joints: telemetry === null ? [] : jointReadoutsFrom(telemetry, offline.side),
    ee: { ...offline.ee, ...POSE_UNREPORTED },
    lastFrameMonoMs: telemetryAtMs ?? NO_FRAME_MONO_MS,
    nowMonoMs: performance.now(),
  };
  return <ManualScreen source={source} />;
}
