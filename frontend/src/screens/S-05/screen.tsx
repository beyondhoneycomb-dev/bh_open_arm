// Teleop screen (WP-G-S05, route /teleop). A FACADE over the TEL domain (05): it
// renders the backend `Teleoperator` / safety-gate state (alignment state machine,
// clutch, delta scales, One-Euro smoother, C-Lat instrumentation, VR link watchdog,
// WebXR entry, PG-VR-001 gate) and sends operator intent (session control, param
// changes, re-engage). It re-implements no domain logic — no clutch-threshold
// decision, no smoother filter math, no deg<->rad, no self-clamp — and holds no
// connect/disconnect/reconnect path (I-2: a browser reconnect would re-zero).
//
// Two safety facts shape the composition. The soft/hard stop is the GLOBAL WP-G-03
// control, not this screen's — `stop_teleop` here is the home-hold session end, not
// a safety stop. And command-source exclusivity (CG-G-S05f) is structural: while a
// VR session is active the param and manual-control affordances are disabled, so no
// UI state lets two sources issue commands at once.

import "./teleop.css";
import { AlignmentStateMachineView } from "./AlignmentStateMachineView";
import { CLatView } from "./CLatView";
import { ClutchBadge } from "./ClutchBadge";
import { CommandSourceBar } from "./CommandSourceBar";
import { HeartbeatWatchdog } from "./HeartbeatWatchdog";
import { LeaderFollowerView } from "./LeaderFollowerView";
import { ScaleControls } from "./ScaleControls";
import { SmootherParamForm } from "./SmootherParamForm";
import { VrSessionView } from "./VrSessionView";
import { WebxrEntryPanel } from "./WebxrEntryPanel";
import { manualControlDisabled, resolveVrEntry } from "./gates";
import { noopCommandSink, type TeleopCommandSink } from "./commands";
import { defaultTeleopSource, type TeleopSource } from "./teleopSource";

export interface TeleopScreenProps {
  source?: TeleopSource;
  commandSink?: TeleopCommandSink;
}

export default function TeleopScreen({
  source = defaultTeleopSource(),
  commandSink = noopCommandSink,
}: TeleopScreenProps) {
  // Session activity gates every parameter affordance: a live VR session is the
  // authoritative command source, so tuning-while-following is disabled to keep the
  // single-source invariant (CG-G-S05f).
  const paramsDisabled = manualControlDisabled(source);
  const vrEntry = resolveVrEntry(source.vrGate);

  return (
    <div className="oa-tel" data-screen="S-05">
      <header className="oa-tel__head">
        <p className="oa-tel__id">/teleop</p>
        <h1 className="oa-tel__title">텔레옵</h1>
      </header>

      <div className="oa-tel__session-ctl" role="group" aria-label="세션 제어">
        <button
          type="button"
          data-field="start-teleop"
          onClick={() => commandSink.send({ op: "start_teleop" })}
        >
          텔레옵 시작
        </button>
        <button
          type="button"
          data-field="stop-teleop"
          onClick={() => commandSink.send({ op: "stop_teleop" })}
        >
          텔레옵 종료 (홈 홀드 · 낙하 없음)
        </button>
        <span className="oa-tel__hint">
          이 종료는 세션 제어이지 안전 정지가 아니다. 소프트/하드 정지는 전역 컨트롤(상시).
        </span>
      </div>

      <CommandSourceBar
        source={source}
        onManualControl={() => {
          /* Manual control is the global WP-G-04 authority path; this button is only
             ever enabled when no VR session holds the command source (CG-G-S05f). */
        }}
      />

      <VrSessionView session={source.session} gate={source.vrGate} />

      <AlignmentStateMachineView
        source={source}
        onReEngage={() => commandSink.send({ op: "re_engage" })}
      />

      <ClutchBadge clutch={source.clutch} />

      <HeartbeatWatchdog watchdog={source.watchdog} />

      <CLatView cLat={source.cLat} />

      <SmootherParamForm
        smoother={source.smoother}
        disabled={paramsDisabled}
        onChange={(minCutoffHz, beta, dCutoff) =>
          commandSink.send({ op: "set_smoother_params", minCutoffHz, beta, dCutoff })
        }
      />

      <ScaleControls
        scale={source.scale}
        disabled={paramsDisabled}
        onPositionScale={(value) => commandSink.send({ op: "set_position_scale", value })}
        onRotationScale={(value) => commandSink.send({ op: "set_rotation_scale", value })}
      />

      <WebxrEntryPanel webxr={source.webxr} resolution={vrEntry} />

      <LeaderFollowerView source={source} />
    </div>
  );
}
