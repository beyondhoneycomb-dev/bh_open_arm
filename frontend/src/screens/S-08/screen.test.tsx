// WP-G-S08 screen composition. It mounts under /datasets via the plugin seam, renders
// every panel that carries a CG-G-S08 gate, and wires the facade intents:
//   - the scrubber drives ONE cursor the plot and camera-sync share (synced playback),
//   - the channel selector re-resolves the plotted series and its unit by name,
//   - dataset/episode/verdict/edit actions emit intents (the backend decides),
//   - the CoW edit intent carries the backend's NEW output repo_id, never the source,
//   - a pending / unlabelled episode shows no fabricated verdict.

import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import DatasetScreen from "./screen";
import { resolveScreen } from "../../routes/screenResolver";
import { defaultDatasetScreenData } from "./datasetSource";
import type { DatasetCommand } from "./commands";
import type { DatasetDataSource, DatasetScreenData } from "./types";

function sourceWith(overrides: Partial<DatasetScreenData>): DatasetDataSource {
  const base = defaultDatasetScreenData();
  return { load: () => ({ ...base, ...overrides }) };
}

function recordingSink(): { sink: { send: (c: DatasetCommand) => void }; sent: DatasetCommand[] } {
  const sent: DatasetCommand[] = [];
  return { sink: { send: (c) => sent.push(c) }, sent };
}

describe("DatasetScreen (WP-G-S08)", () => {
  it("is discovered by the screen resolver at /datasets' S-08 id", () => {
    expect(resolveScreen("S-08")).not.toBeNull();
  });

  it("renders the route id and every gated panel", () => {
    render(<DatasetScreen />);
    expect(screen.getByRole("heading", { name: "데이터셋", level: 1 })).toBeInTheDocument();
    expect(screen.getByText("/datasets")).toBeInTheDocument();
    for (const title of [
      "데이터셋 목록",
      "타임라인",
      "채널 플롯",
      "카메라 동기 재생",
      "캡처 지터",
      "에피소드 라벨",
      "편집 (Copy-on-Write)",
      "검증 리포트",
    ]) {
      expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
    }
  });

  it("drives one cursor the plot and camera sync both read (synced playback)", () => {
    render(<DatasetScreen />);
    const firstStreamKey = defaultDatasetScreenData().cameraStreams[0].imageKey;
    fireEvent.change(screen.getByTestId("scrubber-range"), { target: { value: "4" } });
    expect(screen.getByTestId("scrubber-frame")).toHaveTextContent("4");
    expect(screen.getByTestId("plot-cursor-value")).toHaveTextContent("frame 4");
    expect(screen.getByTestId(`camsync-${firstStreamKey}`)).toHaveAttribute("data-frame", "4");
  });

  it("resolves the plotted channel and its unit by name, not position (CG-G-S08a/g)", () => {
    render(<DatasetScreen />);
    const svg = screen.getByTestId("channel-plot-svg");
    // The default channel is a .pos channel → deg.
    expect(svg).toHaveAttribute("data-unit", "deg");
    // Switch to a torque channel → the axis unit follows the name to Nm.
    fireEvent.change(screen.getByTestId("channel-select"), {
      target: { value: "right_gripper.torque" },
    });
    expect(screen.getByTestId("channel-plot-svg")).toHaveAttribute("data-unit", "Nm");
    expect(screen.getByTestId("plot-axis-label")).toHaveTextContent("right_gripper.torque [Nm]");
  });

  it("reads the success/fail label from the sidecar and never fabricates one (CG-G-S08d)", () => {
    render(<DatasetScreen />);
    // Episode 0: human verdict success is shown.
    expect(screen.getByTestId("verdict-0")).toHaveAttribute("data-verdict", "success");
    // Episode 2: pending_judgment with no verdict → shown unlabelled, not invented.
    expect(screen.getByTestId("verdict-2")).toHaveAttribute("data-verdict", "none");
  });

  it("emits select_dataset / select_episode / set_verdict intents", () => {
    const { sink, sent } = recordingSink();
    render(<DatasetScreen commandSink={sink} />);
    const second = defaultDatasetScreenData().datasets[1].stampedRepoId;
    fireEvent.click(screen.getByTestId(`dataset-${second}`));
    fireEvent.click(within(screen.getByTestId("episode-1")).getByRole("button", { name: /에피소드 1/ }));
    fireEvent.click(within(screen.getByTestId("episode-1")).getByRole("button", { name: "실패 판정" }));
    expect(sent).toEqual([
      { op: "select_dataset", stampedRepoId: second },
      { op: "select_episode", episodeIndex: 1 },
      { op: "set_verdict", episodeIndex: 1, verdict: "fail" },
    ]);
  });

  it("runs a CoW edit to a NEW output repo_id, never the source (CG-G-S08f)", () => {
    const { sink, sent } = recordingSink();
    render(<DatasetScreen commandSink={sink} />);
    const preview = defaultDatasetScreenData().editPreview!;
    expect(screen.getByTestId("edit-output")).toHaveTextContent(preview.outputRepoId);
    expect(preview.outputRepoId).not.toBe(preview.sourceRepoId);
    fireEvent.click(screen.getByTestId("edit-run"));
    expect(sent).toEqual([
      {
        op: "cow_edit",
        operation: preview.operation,
        sourceRepoId: preview.sourceRepoId,
        outputRepoId: preview.outputRepoId,
      },
    ]);
  });

  it("renders the backend verification verdict without recomputing it", () => {
    render(<DatasetScreen source={sourceWith({})} />);
    expect(screen.getByTestId("verify-verdict")).toHaveAttribute("data-verdict", "READY");
  });

  it("shows a missing-check alert when the backend report flags one (INVALID)", () => {
    const base = defaultDatasetScreenData();
    render(
      <DatasetScreen
        source={sourceWith({
          verification: {
            ...base.verification,
            ready: false,
            verdict: "INVALID",
            missingChecks: ["video_frame_count"],
          },
        })}
      />,
    );
    expect(screen.getByTestId("verify-verdict")).toHaveAttribute("data-verdict", "INVALID");
    expect(screen.getByTestId("verify-missing")).toHaveTextContent("video_frame_count");
  });

  it("reports real capture jitter from the capture_ts sidecar (CG-G-S08c)", () => {
    render(<DatasetScreen />);
    // right_wrist sidecar has uneven spacing → non-zero spread (34.8 − 32.3) rendered.
    expect(screen.getByTestId("jitter-value-right_wrist")).toHaveTextContent("2.50 ms");
  });
});
