// WP-G-S10 screen composition. It mounts under /training via the plugin seam, renders
// every panel that carries a CG-G-S10 gate, and wires the facade intents. The render
// tests prove the gates a static scan cannot: the loss curve draws with W&B disabled,
// the checkpoint default is the latest (not min val loss) with the warning always shown,
// and there is no start path while a degenerate finding is undecided.

import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import TrainingScreen from "./screen";
import { resolveScreen } from "../../routes/screenResolver";
import { METRIC_KEYS } from "./metrics";
import { defaultTrainingScreenData } from "./trainingSource";
import type { TrainingCommand } from "./commands";
import type { TrainingDataSource, TrainingScreenData } from "./types";

function sourceWith(overrides: Partial<TrainingScreenData>): TrainingDataSource {
  const base = defaultTrainingScreenData();
  return { load: () => ({ ...base, ...overrides }) };
}

function recordingSink(): { sink: { send: (c: TrainingCommand) => void }; sent: TrainingCommand[] } {
  const sent: TrainingCommand[] = [];
  return { sink: { send: (c) => sent.push(c) }, sent };
}

describe("TrainingScreen (WP-G-S10)", () => {
  it("is discovered by the screen resolver at /training's S-10 id", () => {
    expect(resolveScreen("S-10")).not.toBeNull();
  });

  it("renders the route id and every gated panel", () => {
    render(<TrainingScreen />);
    expect(screen.getByRole("heading", { name: "학습", level: 1 })).toBeInTheDocument();
    expect(screen.getByText("/training")).toBeInTheDocument();
    for (const testid of [
      "job-queue",
      "policy-form",
      "dataset-form",
      "preflight-report",
      "degenerate-review",
      "loss-curve",
      "checkpoint-list",
      "lineage",
    ]) {
      expect(screen.getByTestId(testid)).toBeInTheDocument();
    }
  });

  it("charts only the seven MetricsTracker keys (CG-4A-G1b), no invented option", () => {
    render(<TrainingScreen />);
    const options = within(screen.getByTestId("metric-select")).getAllByRole("option");
    const values = options.map((option) => (option as HTMLOptionElement).value);
    expect([...values].sort()).toEqual([...METRIC_KEYS].sort());
  });

  it("renders the local loss curve with W&B disabled (CG-4A-G1c air-gap)", () => {
    render(<TrainingScreen />);
    expect(screen.getByTestId("wandb-state")).toHaveAttribute("data-wandb-enabled", "false");
    const svg = screen.getByTestId("loss-curve-svg");
    // The curve draws from local samples: a non-empty polyline with points.
    expect(Number(svg.getAttribute("data-points"))).toBeGreaterThan(0);
    expect(screen.getByTestId("loss-curve-line").getAttribute("points")).toBeTruthy();
  });

  it("defaults the checkpoint to the latest, not the min val loss, and always warns (CG-4A-G1d)", () => {
    render(<TrainingScreen />);
    const list = screen.getByTestId("checkpoint-list");
    const defaultStep = list.getAttribute("data-default-step");
    const minValLossStep = list.getAttribute("data-min-valloss-step");
    expect(defaultStep).toBe("8000");
    expect(minValLossStep).toBe("6000");
    expect(defaultStep).not.toBe(minValLossStep);
    expect(screen.getByTestId(`checkpoint-${defaultStep}`)).toHaveAttribute("data-selected", "true");
    expect(screen.getByTestId(`checkpoint-${minValLossStep}`)).toHaveAttribute("data-selected", "false");
    expect(screen.getByTestId("offline-metric-warning").textContent).toContain("온라인 성공률");
  });

  it("has no start path while a degenerate finding is undecided (CG-4A-G1e)", () => {
    const { sink, sent } = recordingSink();
    render(<TrainingScreen commandSink={sink} />);
    const start = screen.getByTestId("start-training");
    expect(start).toBeDisabled();
    expect(screen.getByTestId("start-block-reasons").textContent).toContain("FR-TRN-068");
    // Clicking the disabled control emits nothing.
    fireEvent.click(start);
    expect(sent.some((command) => command.op === "create_job")).toBe(false);
  });

  it("has no resume-to-start path while a degenerate finding is undecided (CG-4A-G1e)", () => {
    const { sink, sent } = recordingSink();
    render(<TrainingScreen commandSink={sink} />);
    // The gate is closed (undecided degenerate). A checkpoint resume still starts a run,
    // so it must obey the same gate: the resume button is disabled and emits nothing.
    const resume = screen.getByTestId("checkpoint-resume-8000");
    expect(resume).toBeDisabled();
    fireEvent.click(resume);
    expect(sent.some((command) => command.op === "create_job")).toBe(false);
  });

  it("enables start only after the degenerate three-way choice is made (CG-4A-G1e)", () => {
    const { sink, sent } = recordingSink();
    render(<TrainingScreen commandSink={sink} />);
    const finding = defaultTrainingScreenData().degenerateFindings[0];
    fireEvent.click(
      screen.getByTestId(`degenerate-choice-${finding.channelName}-EXCLUDE`),
    );
    expect(sent.some((command) => command.op === "resolve_degenerate")).toBe(true);
    const start = screen.getByTestId("start-training");
    expect(start).not.toBeDisabled();
    fireEvent.click(start);
    const created = sent.find((command) => command.op === "create_job");
    expect(created).toBeTruthy();
  });

  it("marks a GPU-absent QUEUED job distinctly from an awaiting-preflight one (CG-G-S10h)", () => {
    render(<TrainingScreen />);
    const jobs = defaultTrainingScreenData().jobs;
    const gpuWait = jobs.find((job) => job.queuedReason === "awaiting_gpu")!;
    const preflightWait = jobs.find((job) => job.queuedReason === "awaiting_preflight")!;
    const gpuCell = screen.getByTestId(`job-state-${gpuWait.jobId}`);
    const preflightCell = screen.getByTestId(`job-state-${preflightWait.jobId}`);
    expect(gpuCell).toHaveAttribute("data-queued-reason", "awaiting_gpu");
    expect(preflightCell).toHaveAttribute("data-queued-reason", "awaiting_preflight");
    expect(gpuCell.textContent).not.toBe(preflightCell.textContent);
  });

  it("shows blocked policies with their source and a runtime-derived provenance (CG-G-S10a/e)", () => {
    render(<TrainingScreen />);
    expect(screen.getByTestId("policy-provenance").textContent).toContain("런타임 유도");
    const blocked = defaultTrainingScreenData().policies.filter((option) => option.blocked);
    expect(blocked.length).toBeGreaterThan(0);
    for (const option of blocked) {
      const id = option.capability.id;
      expect(screen.getByTestId(`policy-blocked-${id}`)).toBeInTheDocument();
      expect(screen.getByTestId(`policy-source-${id}`).textContent).toContain("출처");
      expect(screen.getByTestId(`policy-radio-${id}`)).toBeDisabled();
    }
  });

  it("surfaces an unavailable policy as blocked (CG-G-S10g)", () => {
    render(<TrainingScreen />);
    const unavailable = defaultTrainingScreenData().policies.find(
      (option) => !option.capability.available,
    )!;
    expect(screen.getByTestId(`policy-blocked-${unavailable.capability.id}`)).toBeInTheDocument();
    expect(screen.getByTestId(`policy-radio-${unavailable.capability.id}`)).toBeDisabled();
  });

  it("shows the VRAM source, and disables start with alternatives when it does not fit (CG-G-S10e)", () => {
    render(<TrainingScreen />);
    expect(screen.getByTestId("vram-source").textContent).toContain("출처");

    const { sink, sent } = recordingSink();
    render(
      <TrainingScreen
        commandSink={sink}
        source={sourceWith({
          degenerateFindings: [],
          vram: {
            fits: false,
            requiredGb: 22,
            availableGb: 16,
            source: "nvidia-smi (RTX 5080)",
            alternatives: ["LoRA 어댑터로 학습", "배치 크기 축소"],
          },
        })}
      />,
    );
    const starts = screen.getAllByTestId("start-training");
    const start = starts[starts.length - 1];
    expect(start).toBeDisabled();
    expect(screen.getByTestId("vram-alternatives").textContent).toContain("LoRA");
    fireEvent.click(start);
    expect(sent.some((command) => command.op === "create_job")).toBe(false);
  });

  it("guides multi-dataset use to the merge path and offers no dataset list control (CG-G-S10f)", () => {
    render(<TrainingScreen />);
    expect(screen.getByTestId("merge-note").textContent).toContain("병합");
    // The dataset selector is single-choice radios, never a multi-select listbox.
    const radios = screen.getAllByRole("radio");
    expect(radios.length).toBeGreaterThan(0);
  });

  it("renders a BLOCK preflight with its located findings (facade)", () => {
    render(
      <TrainingScreen
        source={sourceWith({
          preflight: {
            verdict: "BLOCK",
            findings: [
              {
                code: "OBSERVATION_STATE_ORDER",
                channelName: "right_joint_2.vel",
                component: ".vel",
                joint: "right_joint_2",
                detail: "names order does not match the canonical per-motor layout",
              },
            ],
          },
        })}
      />,
    );
    expect(screen.getByTestId("preflight-verdict")).toHaveAttribute("data-verdict", "BLOCK");
    expect(screen.getByTestId("preflight-findings").textContent).toContain("right_joint_2");
  });

  it("emits query and cancel intents from the job queue", () => {
    const { sink, sent } = recordingSink();
    render(<TrainingScreen commandSink={sink} />);
    fireEvent.change(screen.getByTestId("job-name-filter"), { target: { value: "pick" } });
    const runningJob = defaultTrainingScreenData().jobs.find((job) => job.state === "RUNNING")!;
    fireEvent.click(screen.getByTestId(`job-cancel-${runningJob.jobId}`));
    expect(sent.some((command) => command.op === "query_jobs")).toBe(true);
    expect(sent).toContainEqual({ op: "cancel_job", jobId: runningJob.jobId });
  });
});
