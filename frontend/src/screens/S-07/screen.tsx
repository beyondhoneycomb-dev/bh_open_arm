// Data-collection screen (WP-G-S07, route /collect). A FACADE over the REC domain
// (07): it renders the backend recorder's state and sends episode-control intent,
// and it re-implements none of the recorder's logic (02d §2.2). The episode-loop
// FSM, the drop report (WS-transmit drops kept separate from capture/encode drops),
// the stamped dataset name, the storage prediction, Resume, and the WP-3C gate
// states are all rendered from backend/global data. Two invariants are structural:
// the session-stop control is `session_stop`, never the safety E-Stop (CG-G-S07a),
// and the screen opens no socket and offers no reconnect (I-2).

import { useMemo, useState } from "react";

import "./collect.css";
import { PushToHubBadge, PushToHubConfirm } from "../../global";
import { DatasetIdentityView } from "./DatasetIdentityView";
import { DropReportView } from "./DropReportView";
import { EpisodeLoopView } from "./EpisodeLoopView";
import { GateStatusView } from "./GateStatusView";
import { ResumeView } from "./ResumeView";
import { StoragePredictionView } from "./StoragePredictionView";
import { TaskPromptView } from "./TaskPromptView";
import { commandForEvent, nextPhase, type EpisodeEvent, type EpisodePhase } from "./episodeFsm";
import { needsPushToHubConfirm, startBlocked } from "./startGate";
import { noopCommandSink, type RecorderCommandSink } from "./commands";
import { defaultCollectSource } from "./collectSource";
import type { CollectDataSource } from "./types";

export interface CollectScreenProps {
  source?: CollectDataSource;
  commandSink?: RecorderCommandSink;
}

const DEFAULT_SOURCE: CollectDataSource = defaultCollectSource();

export default function CollectScreen({
  source,
  commandSink = noopCommandSink,
}: CollectScreenProps) {
  const resolved = source ?? DEFAULT_SOURCE;
  const data = useMemo(() => resolved.load(), [resolved]);

  const [phase, setPhase] = useState<EpisodePhase>(data.sessionActive ? "recording" : "idle");
  const [pushConfirmOpen, setPushConfirmOpen] = useState(false);

  const blocked = startBlocked(data.preflight, data.storage);
  const canStart = !blocked;

  // Apply one FSM transition: advance the view phase and emit the event's intent
  // (some events, like `advance`/"repeat", carry no command). The backend is the
  // authority that accepts or refuses the intent.
  function applyEvent(event: EpisodeEvent): void {
    const to = nextPhase(phase, event);
    if (to === null) {
      return;
    }
    const command = commandForEvent(event, data.taskPrompt.text);
    if (command !== null) {
      commandSink.send(command);
    }
    setPhase(to);
  }

  // `start` is the one event routed through the start gate: it is blocked below the
  // gate and, when push_to_hub is on, deferred behind the explicit confirm
  // (CG-G-S07f) before the session_start intent is sent.
  function handleEvent(event: EpisodeEvent): void {
    if (event === "start") {
      if (!canStart) {
        return;
      }
      if (needsPushToHubConfirm(data.pushToHub)) {
        setPushConfirmOpen(true);
        return;
      }
    }
    applyEvent(event);
  }

  function confirmPushToHub(): void {
    setPushConfirmOpen(false);
    applyEvent("start");
  }

  function changeTask(task: string): void {
    commandSink.send({ op: "set_task", task });
  }

  function resumeSession(stampedRepoId: string): void {
    commandSink.send({ op: "resume", stampedRepoId });
  }

  return (
    <div className="oa-collect" data-screen="S-07">
      <header className="oa-collect__head">
        <p className="oa-collect__id">/collect</p>
        <h1 className="oa-collect__title">데이터 수집</h1>
        <PushToHubBadge state={data.pushToHub} />
      </header>

      <DatasetIdentityView dataset={data.dataset} />
      <TaskPromptView prompt={data.taskPrompt} editable={phase === "idle"} onChange={changeTask} />

      <EpisodeLoopView
        phase={phase}
        events={data.events}
        recordedEpisodeCount={data.recordedEpisodeCount}
        canStart={canStart}
        onEvent={handleEvent}
      />

      {pushConfirmOpen && (
        <PushToHubConfirm
          state={data.pushToHub}
          onConfirm={confirmPushToHub}
          onCancel={() => setPushConfirmOpen(false)}
        />
      )}

      <StoragePredictionView storage={data.storage} />
      <DropReportView report={data.dropReport} />
      <ResumeView sessions={data.resumable} onResume={resumeSession} />
      <GateStatusView gates={data.gates} />
    </div>
  );
}
