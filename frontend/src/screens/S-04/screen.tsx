// Manual-motion screen (WP-G-S04, route /manual). A FACADE over the MAN domain
// (04): it renders backend state and sends operator intent. The jog math, the
// two-stage clamp, the velocity/step guards and the stop category are the
// backend's — this screen implements none of them (CG-G-S04a).
//
// One gate governs every motion emission. A jog press, a slider drag, a 3D
// interaction — none issues a command until torque is explicitly armed AND the
// control lease is held AND the stream is fresh (CG-G-S04b). All motion intents
// route through emitMotion; Freedrive and arming route through the lease-only
// gate. The screen never calls connect()/disconnect() and offers no reconnect
// (I-2): arming is enable_torque, not a session re-open.

import { useState } from "react";

import "./manual.css";
import { ViewportPanel } from "../../viewport";
import { CartesianPanel } from "./CartesianPanel";
import { ElbowSlider } from "./ElbowSlider";
import { FreedriveBanner } from "./FreedriveBanner";
import { FreedriveDeadman } from "./FreedriveDeadman";
import { HomePanel } from "./HomePanel";
import { JogPanel } from "./JogPanel";
import { LeaseHeartbeatBar } from "./LeaseHeartbeatBar";
import { TeachReplayPanel } from "./TeachReplayPanel";
import { canArm, canIssueMotion, leaseHeld, streamStale } from "./gating";
import { noopCommandSink, type ManualCommand, type ManualCommandSink, type JogMode, type ReferenceFrame } from "./commands";
import { defaultManualSource, type ManualSource } from "./manualSource";

export interface ManualScreenProps {
  source?: ManualSource;
  commandSink?: ManualCommandSink;
  // Teach-store intents (backend REST). Defaulted to no-ops for the offline lane;
  // the backend owns the teach list, so these are calls, not local mutations.
  onTeachCapture?: () => void;
  onTeachDelete?: (id: string) => void;
  onTeachDuplicate?: (id: string) => void;
  onTeachReorder?: (id: string, direction: "up" | "down") => void;
}

const NOOP = (): void => {};

export default function ManualScreen({
  source = defaultManualSource(),
  commandSink = noopCommandSink,
  onTeachCapture = NOOP,
  onTeachDelete = NOOP,
  onTeachDuplicate = NOOP,
  onTeachReorder = NOOP,
}: ManualScreenProps) {
  const [armed, setArmed] = useState(false);
  const [jogMode, setJogMode] = useState<JogMode>("continuous");
  const [jogStepSizeDeg, setJogStepSizeDeg] = useState(source.jogStepSizesDeg[0]);
  const [speedScalePct, setSpeedScalePct] = useState(source.speedScalePctDefault);
  const [cartMode, setCartMode] = useState<JogMode>("continuous");
  const [activeFrame, setActiveFrame] = useState<ReferenceFrame>(source.cartesian.activeFrame);
  const [translationStepMm, setTranslationStepMm] = useState(source.cartesian.translationStepsMm[0]);
  const [rotationStepDeg, setRotationStepDeg] = useState(source.cartesian.rotationStepsDeg[0]);
  const [elbowValue, setElbowValue] = useState(0);
  const [homeProfileId, setHomeProfileId] = useState(source.home.activeProfileId);

  const armGate = canArm(source);
  const moveGate = canIssueMotion(source, armed);
  const held = leaseHeld(source);
  const stale = streamStale(source);

  // The single motion gate: every jog/elbow/replay/home intent passes here, so an
  // unarmed or stale interaction emits nothing (CG-G-S04b).
  function emitMotion(command: ManualCommand): void {
    if (moveGate) {
      commandSink.send(command);
    }
  }

  // Arming and Freedrive need control authority and a fresh stream, but not the
  // arm toggle itself; they use the lease-only gate.
  function toggleArm(): void {
    if (!armGate) {
      return;
    }
    const next = !armed;
    setArmed(next);
    commandSink.send({ op: next ? "enable_torque" : "disable_torque", side: source.side });
  }

  function emitFreedrive(kind: "freedrive_enter" | "freedrive_exit"): void {
    if (armGate) {
      commandSink.send({ op: kind, side: source.side });
    }
  }

  return (
    <div className="oa-man" data-screen="S-04">
      <FreedriveBanner status={source.freedrive} currentScreen="S-04" />

      <header className="oa-man__head">
        <p className="oa-man__id">/manual</p>
        <h1 className="oa-man__title">수동 동작</h1>
      </header>

      <LeaseHeartbeatBar source={source} />

      <div className="oa-man__arm" role="group" aria-label="암/인에이블">
        <button
          type="button"
          className="oa-man__arm-toggle"
          data-field="arm-toggle"
          data-armed={armed ? "true" : "false"}
          disabled={!armGate}
          aria-pressed={armed}
          onClick={toggleArm}
        >
          {armed ? "인에이블 해제 (토크 OFF)" : "암/인에이블 (토크 ON)"}
        </button>
        <p className="oa-man__gate" role="status" data-field="control-gate">
          제어 입력: {moveGate ? "허용" : "차단"}
          {!held && " · 리스 미보유"}
          {stale && " · STALE"}
          {!armed && " · 미암드"}
        </p>
      </div>

      <ViewportPanel source={source.viewport} />

      <JogPanel
        source={source}
        mode={jogMode}
        onModeChange={setJogMode}
        stepSizeDeg={jogStepSizeDeg}
        onStepSizeChange={setJogStepSizeDeg}
        speedScalePct={speedScalePct}
        onSpeedScaleChange={setSpeedScalePct}
        canMove={moveGate}
        onCommand={emitMotion}
      />

      <CartesianPanel
        source={source}
        mode={cartMode}
        onModeChange={setCartMode}
        activeFrame={activeFrame}
        onFrameChange={setActiveFrame}
        translationStepMm={translationStepMm}
        onTranslationStepChange={setTranslationStepMm}
        rotationStepDeg={rotationStepDeg}
        onRotationStepChange={setRotationStepDeg}
        speedScalePct={speedScalePct}
        canMove={moveGate}
        onCommand={emitMotion}
      />

      <ElbowSlider
        side={source.side}
        value={elbowValue}
        onValueChange={setElbowValue}
        onCommand={emitMotion}
      />

      <FreedriveDeadman
        status={source.freedrive}
        enabled={armGate}
        onEnter={() => emitFreedrive("freedrive_enter")}
        onExit={() => emitFreedrive("freedrive_exit")}
      />

      <TeachReplayPanel
        teach={source.teach}
        side={source.side}
        canMove={moveGate}
        onCapture={onTeachCapture}
        onDelete={onTeachDelete}
        onDuplicate={onTeachDuplicate}
        onReorder={onTeachReorder}
        onCommand={emitMotion}
      />

      <HomePanel
        home={source.home}
        side={source.side}
        activeProfileId={homeProfileId}
        onProfileChange={setHomeProfileId}
        canMove={moveGate}
        onCommand={emitMotion}
      />
    </div>
  );
}
