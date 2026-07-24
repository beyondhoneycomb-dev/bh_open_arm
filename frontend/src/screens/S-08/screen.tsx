// Dataset screen (WP-G-S08, route /datasets). A FACADE over the DAT domain (08): it
// renders the Wave 3D backend's dataset outputs — the browse inventory, the timeline
// scrubber, the observation.state channel plot, camera-synced playback, the capture_ts
// jitter sidecar, the episode label sidecar, the copy-on-write edit preview and the
// integrity verification report — and emits selection/verdict/edit intent. It owns no
// domain truth: the channel index comes from info.json `names`, the CoW copy and the
// integrity verdict are the backend's, and the screen recomputes none of them.
//
// Like the sibling screens it renders from a `source` prop with an offline default
// fixture and a `commandSink` that defaults to a no-op, so the WP is verifiable
// against fixtures without a backend (AI-offline). The screen resolver mounts it with
// no props; a later integration wave wires live WS/file-read state in. It opens no
// socket and offers no reconnect (invariant I-2).
//
// The gates this screen keeps, and where each is kept:
//   - CG-G-S08a state channel resolved by `names` index, no fixed index → channels / ChannelPlotView
//   - CG-G-S08b no observation.effort reference                          → (absent everywhere)
//   - CG-G-S08c timestamp is synthetic, jitter from capture_ts sidecar   → TimelineScrubberView / CaptureJitterView
//   - CG-G-S08d success/fail label read from the sidecar                 → EpisodeLabelView
//   - CG-G-S08e no export/convert UI path                                → commands (op set) / (absent)
//   - CG-G-S08f edit is copy-on-write only, no in-place path             → CowEditView / commands
//   - CG-G-S08g per-channel unit axis labels (deg / deg/s / Nm)          → channels / ChannelPlotView

import { useMemo, useState } from "react";

import "./datasets.css";
import { CameraSyncView } from "./CameraSyncView";
import { CaptureJitterView } from "./CaptureJitterView";
import { ChannelPlotView } from "./ChannelPlotView";
import { CowEditView } from "./CowEditView";
import { DatasetBrowseView } from "./DatasetBrowseView";
import { EpisodeLabelView } from "./EpisodeLabelView";
import { TimelineScrubberView } from "./TimelineScrubberView";
import { VerificationReportView } from "./VerificationReportView";
import { defaultDatasetSource } from "./datasetSource";
import { noopCommandSink, type DatasetCommandSink } from "./commands";
import type { DatasetDataSource, EditPreview } from "./types";

export interface DatasetScreenProps {
  source?: DatasetDataSource;
  commandSink?: DatasetCommandSink;
}

const DEFAULT_SOURCE: DatasetDataSource = defaultDatasetSource();

export default function DatasetScreen({
  source,
  commandSink = noopCommandSink,
}: DatasetScreenProps) {
  const resolved = source ?? DEFAULT_SOURCE;
  const data = useMemo(() => resolved.load(), [resolved]);

  // View-local cursor and channel selection. These are presentation state, not domain
  // state: the frame cursor is shared by the plot and the camera sync so they stay in
  // step, and the channel is one of the dataset's `names`. Neither is sent to the
  // backend; dataset/episode/verdict/edit choices are.
  const [cursorFrame, setCursorFrame] = useState(0);
  const [selectedChannel, setSelectedChannel] = useState(data.signals.stateNames[0]);

  function selectDataset(stampedRepoId: string): void {
    commandSink.send({ op: "select_dataset", stampedRepoId });
  }

  function selectEpisode(episodeIndex: number): void {
    commandSink.send({ op: "select_episode", episodeIndex });
  }

  function setVerdict(episodeIndex: number, verdict: "success" | "fail"): void {
    commandSink.send({ op: "set_verdict", episodeIndex, verdict });
  }

  function runEdit(preview: EditPreview): void {
    commandSink.send({
      op: "cow_edit",
      operation: preview.operation,
      sourceRepoId: preview.sourceRepoId,
      outputRepoId: preview.outputRepoId,
    });
  }

  return (
    <div className="oa-ds" data-screen="S-08">
      <header className="oa-ds__head">
        <p className="oa-ds__id">/datasets</p>
        <h1 className="oa-ds__title">데이터셋</h1>
      </header>

      <DatasetBrowseView
        datasets={data.datasets}
        selectedRepoId={data.selectedRepoId}
        onSelect={selectDataset}
      />

      <div className="oa-ds__playback">
        <TimelineScrubberView
          timeAxis={data.signals.timeAxis}
          cursorFrame={cursorFrame}
          onScrub={setCursorFrame}
        />
        <ChannelPlotView
          signals={data.signals}
          selectedChannel={selectedChannel}
          cursorFrame={cursorFrame}
          onSelectChannel={setSelectedChannel}
        />
        <CameraSyncView streams={data.cameraStreams} cursorFrame={cursorFrame} />
      </div>

      <CaptureJitterView sidecars={data.captureJitter} />

      <EpisodeLabelView
        episodes={data.episodes}
        selectedEpisodeIndex={data.selectedEpisodeIndex}
        onSelectEpisode={selectEpisode}
        onSetVerdict={setVerdict}
      />

      <CowEditView preview={data.editPreview} onRunEdit={runEdit} />

      <VerificationReportView report={data.verification} />
    </div>
  );
}
