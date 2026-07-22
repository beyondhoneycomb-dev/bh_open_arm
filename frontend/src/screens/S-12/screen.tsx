// S-12 collision/safety screen (route /safety). The window onto SAF (12): it
// renders the backend's safety state — the friction gate, the forced detection
// status, the applied reaction mode, the GMO residuals against their thresholds,
// the contact list, the injected virtual walls, and the event ring buffer — and
// emits operator intent. It owns no domain truth: no clamp, no unit conversion,
// no collision judgement (the thresholds, the reaction enforcement, and the
// collision check all live in the backend).
//
// Like the shared viewport, it renders from a `source` prop with an offline
// default fixture and calls intent callbacks that default to no-ops, so the WP is
// verifiable against fixtures without a backend (AI-offline). The screen resolver
// mounts it with no props; a later integration wave wires live WS state in.
//
// The four safety invariants this screen must not break, and where each is kept:
//   - default reaction is STOP_HOLD, never a power cut (CG-G-S12a) → reactionPolicy
//   - detection cannot be enabled while PG-FRIC-001 is unmet (CG-G-S12b) → detectionGate
//   - residual and threshold share one plot (CG-G-S12c) → ResidualPlot
//   - a wall edit reaches the scene only via the geom injector (CG-G-S12d) → VirtualWallEditor
//   - intrusion/imminent is highlighted from backend depth (CG-G-S12e) → ContactList

import "./safetyScreen.css";
import { ContactList } from "./ContactList";
import { DetectionPanel } from "./DetectionPanel";
import { EventLog } from "./EventLog";
import { ReactionPolicySelector } from "./ReactionPolicySelector";
import { ResidualPlot } from "./ResidualPlot";
import { VirtualWallEditor } from "./VirtualWallEditor";
import { evaluateDetectionGate } from "./detectionGate";
import {
  defaultSafetyScreenSource,
  noopIntents,
  type SafetyScreenIntents,
  type SafetyScreenSource,
} from "./source";

interface SafetyScreenProps {
  source?: SafetyScreenSource;
  intents?: SafetyScreenIntents;
}

export default function SafetyScreen({
  source = defaultSafetyScreenSource(),
  intents = noopIntents(),
}: SafetyScreenProps) {
  const gate = evaluateDetectionGate({
    frictionGate: source.frictionGate,
    torqueObservationEnabled: source.torqueObservationEnabled,
  });

  return (
    <div className="oa-safety">
      <header className="oa-safety__head">
        <span className="oa-safety__id">/safety</span>
        <h1 className="oa-safety__title">충돌 · 안전</h1>
      </header>

      <DetectionPanel
        status={source.detectionStatus}
        gate={gate}
        onEnableDetection={intents.onEnableDetection}
      />

      <div className="oa-safety__grid">
        <ReactionPolicySelector
          backendMode={source.reactionMode}
          onSelectReaction={intents.onSelectReaction}
        />
        <ResidualPlot residuals={source.residuals} />
      </div>

      <VirtualWallEditor
        walls={source.walls}
        onInjectWall={intents.onInjectWall}
        onRemoveWall={intents.onRemoveWall}
      />

      <div className="oa-safety__grid">
        <ContactList contacts={source.contacts} />
        <EventLog
          events={source.events}
          nowMonoMs={source.nowMonoMs}
          onAcknowledgeEvent={intents.onAcknowledgeEvent}
        />
      </div>
    </div>
  );
}
