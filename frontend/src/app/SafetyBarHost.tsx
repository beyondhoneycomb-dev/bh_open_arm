// The shell's mount of the always-on safety surface (WP-G-03), plus the two handlers
// the surface needs. The shell owns the handlers because they are outbound backend
// calls, and WP-G-03 owns no transport.
//
// Every value passed down is what is TRUE with no session open: nothing is connected,
// so no badge reports a mode, a profile, a control holder, a CAN interface, or a flag
// value. None of these is a placeholder to be replaced by a cheerful default later —
// they are the honest reading of an unconnected shell, and the types admit them.
//
// Both handlers report failure where the operator can see it. A stop that silently does
// nothing is the defect NORM-007 rules on directly, and the same reasoning applies to a
// flag toggle: neither may redraw itself as though it had taken effect.

import { useCallback, useState } from "react";
import { useLocation } from "react-router-dom";

import {
  GlobalSafetyBar,
  type CanInterfaceStatus,
  type Notification,
  type PushToHubState,
  type RobotBadgeState,
  type VelocityTorqueState,
} from "../global";
import {
  STOP_HOLD_SENDER,
  VELOCITY_TORQUE_WRITER,
  deliver,
  type CommandOutcome,
} from "./backendLink";
import { useRealtime } from "./RealtimeContext";
import { screenIdForPath } from "./currentScreen";
import type { TelemetryView } from "../ws/telemetryView";

// What the badge bar shows before any telemetry has arrived, and after the link goes away.
// `connected: false` is a fact rather than a pessimistic guess: the provider clears its last
// frame when the channel closes, so a null view means nothing is arriving right now.
const NO_SESSION_ROBOT: RobotBadgeState = {
  connected: false,
  mode: null,
  profileName: null,
  controlHolder: null,
};

// Derive the badge state from what the frame actually carries, which is one field of the four.
//
// `mode`, `profileName` and `controlHolder` stay unobserved because the telemetry frame has no
// channel for them — the mode is the session's, the profile is the config's, and the holder is
// the lease's. Filling any of them from what IS here would be a label with nothing behind it.
//
// Staleness is not judged. A reading's age is on the wire (`readAgeS`) and no threshold has been
// decided for it, so this reports what arrived rather than a verdict nobody chose. What it does
// catch is a link that stopped: the provider drops its view with the channel, and the bar falls
// back to the constant above.
function robotBadgeFrom(telemetry: TelemetryView | null): RobotBadgeState {
  if (telemetry === null || telemetry.arms.length === 0) {
    return NO_SESSION_ROBOT;
  }
  return { ...NO_SESSION_ROBOT, connected: true };
}

// Empty because no interface has been observed, not because none exists. The badge bar
// renders this absence explicitly rather than showing zero CAN badges.
const NO_SESSION_CAN: readonly CanInterfaceStatus[] = [];

// Both config flags are unread: the GUI has fetched no config.
const NO_SESSION_VELOCITY_TORQUE: VelocityTorqueState = { enabled: null };
const NO_SESSION_PUSH_TO_HUB: PushToHubState = { enabled: null, private: null, tags: [] };

const NO_SESSION_NOTIFICATIONS: readonly Notification[] = [];

// Not dummy mode. Dummy mode is a specific backend configuration — the enactic dummy
// node — and claiming it would name a backend that is not running. The absence of any
// backend is carried by the disconnected badge and the missing-link notice below.
const DUMMY_MODE = false;

const STOP_LINK_ABSENT_NOTICE =
  "이 소프트 스톱은 아직 전달 경로가 없습니다 — 누르더라도 로봇에 도달하지 않습니다. 즉시 정지가 필요하면 전원라인 물리 E-Stop을 사용하십시오.";
const STOP_FAILED_HEADLINE = "소프트 스톱이 전달되지 않았습니다";
const FLAG_FAILED_HEADLINE = "설정이 적용되지 않았습니다";

export function SafetyBarHost() {
  const { pathname } = useLocation();
  const { telemetry } = useRealtime();
  const [stopOutcome, setStopOutcome] = useState<CommandOutcome | null>(null);
  const [flagOutcome, setFlagOutcome] = useState<CommandOutcome | null>(null);

  const handleSoftStop = useCallback(() => {
    setStopOutcome(deliver(STOP_HOLD_SENDER));
  }, []);

  // The requested value is passed to the writer and never mirrored into local state: with
  // no writer the flag's value is still unread, and showing the operator's click as the
  // new value would invent a config the backend never received.
  const handleToggleVelocityTorque = useCallback((enabled: boolean) => {
    const writer = VELOCITY_TORQUE_WRITER;
    setFlagOutcome(deliver(writer ? () => writer(enabled) : null));
  }, []);

  return (
    <div className="oa-safety-host">
      <GlobalSafetyBar
        context={{ screen: screenIdForPath(pathname), mode: null, role: null }}
        robot={robotBadgeFrom(telemetry)}
        canInterfaces={NO_SESSION_CAN}
        velocityTorque={NO_SESSION_VELOCITY_TORQUE}
        pushToHub={NO_SESSION_PUSH_TO_HUB}
        notifications={NO_SESSION_NOTIFICATIONS}
        dummyMode={DUMMY_MODE}
        onSoftStop={handleSoftStop}
        onToggleVelocityTorque={handleToggleVelocityTorque}
      />

      {STOP_HOLD_SENDER === null && (
        <p className="oa-link-notice" role="status" data-stop-link="absent">
          {STOP_LINK_ABSENT_NOTICE}
        </p>
      )}

      {stopOutcome && !stopOutcome.sent && (
        <p className="oa-link-failure" role="alert" data-stop-delivery="failed">
          <strong className="oa-link-failure__head">{STOP_FAILED_HEADLINE}</strong>
          <span className="oa-link-failure__why">{stopOutcome.reason}</span>
        </p>
      )}

      {flagOutcome && !flagOutcome.sent && (
        <p className="oa-link-failure" role="alert" data-flag-write="failed">
          <strong className="oa-link-failure__head">{FLAG_FAILED_HEADLINE}</strong>
          <span className="oa-link-failure__why">{flagOutcome.reason}</span>
        </p>
      )}
    </div>
  );
}
