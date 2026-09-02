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
// Connected means a reading is still advancing, which is not the same as frames still arriving.
// The two come apart when the loop that fills the board dies while the socket stays up: the
// server keeps publishing the last reading at the full rate, so a badge that counted frames
// reports a healthy arm for as long as the operator leaves the page open. The server judges the
// age against the tick rate it set and puts the verdict in the frame; this reads it.
function robotBadgeFrom(telemetry: TelemetryView | null): RobotBadgeState {
  if (telemetry === null || telemetry.arms.every((arm) => arm.stale)) {
    return NO_SESSION_ROBOT;
  }
  return { ...NO_SESSION_ROBOT, connected: true };
}

// Whether frames are arriving from arms whose readings have all stopped advancing. Distinct from
// the disconnected badge on purpose: the badge cannot separate "no arm" from "an arm that froze",
// and those want opposite things from the operator — one is a session not started, the other is a
// rig that needs looking at.
function readingStopped(telemetry: TelemetryView | null): boolean {
  return telemetry !== null && telemetry.arms.length > 0 && telemetry.arms.every((arm) => arm.stale);
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

const READING_STOPPED_HEADLINE = "팔 상태 읽기가 멈췄습니다";
const READING_STOPPED_WHY =
  "화면의 값은 마지막으로 읽힌 것이고 더 갱신되지 않습니다. 서버가 팔을 계속 읽고 있는지 stderr 로그를 확인하십시오.";

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

      {readingStopped(telemetry) && (
        <p className="oa-link-failure" role="alert" data-arm-reading="stopped">
          <strong className="oa-link-failure__head">{READING_STOPPED_HEADLINE}</strong>
          <span className="oa-link-failure__why">{READING_STOPPED_WHY}</span>
        </p>
      )}

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
