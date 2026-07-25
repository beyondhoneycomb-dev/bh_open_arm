// WP-G-S11 screen composition. It mounts under /inference via the plugin seam, renders
// every panel that carries a CG-G-S11 gate, and wires the facade intents. These render
// tests prove the gates a static scan cannot: the control UI locks on a schema mismatch,
// the success rate is never a bare point estimate (and vanishes during the 2-landing
// window), N<20 is flagged and unranked, the action-queue size is live-bound, LOCAL and
// ASYNC start through the one path, and the Orin+GR00T verdict blocks sync and
// trt_full_pipeline while a fail-blocking IK gate renders a target unsupported.

import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import InferenceScreen from "./screen";
import { resolveScreen } from "../../routes/screenResolver";
import { defaultInferenceScreenData } from "./inferenceSource";
import { STATISTICALLY_MEANINGLESS_LABEL } from "./types";
import type { InferenceCommand } from "./commands";
import type {
  ActionQueueTelemetry,
  InferenceDataSource,
  InferenceScreenData,
  QueueTelemetrySource,
} from "./types";

function sourceWith(overrides: Partial<InferenceScreenData>): InferenceDataSource {
  const base = defaultInferenceScreenData();
  return { load: () => ({ ...base, ...overrides }) };
}

function recordingSink(): { sink: { send: (c: InferenceCommand) => void }; sent: InferenceCommand[] } {
  const sent: InferenceCommand[] = [];
  return { sink: { send: (c) => sent.push(c) }, sent };
}

// A queue-telemetry source a test can drive frame by frame, to prove the action-queue size
// is bound to the live stream (CG-G-S11f) and not baked at load.
function controllableQueueSource(initial: ActionQueueTelemetry): {
  source: QueueTelemetrySource;
  push: (telemetry: ActionQueueTelemetry) => void;
} {
  let current: ((telemetry: ActionQueueTelemetry) => void) | null = null;
  const source: QueueTelemetrySource = {
    initial: () => initial,
    subscribe: (listener) => {
      current = listener;
      return () => {
        current = null;
      };
    },
  };
  return {
    source,
    push: (telemetry) =>
      act(() => {
        if (current) {
          current(telemetry);
        }
      }),
  };
}

describe("InferenceScreen (WP-G-S11)", () => {
  it("is discovered by the screen resolver at /inference's S-11 id", () => {
    expect(resolveScreen("S-11")).not.toBeNull();
  });

  it("renders the route id and every gated panel", () => {
    render(<InferenceScreen />);
    expect(screen.getByRole("heading", { name: "추론/평가", level: 1 })).toBeInTheDocument();
    expect(screen.getByText("/inference")).toBeInTheDocument();
    for (const testid of [
      "schema-negotiation",
      "inference-loop",
      "action-queue",
      "deploy-matrix",
      "mode-selector",
      "task-switcher",
      "takeover-control",
      "rollout-control",
      "success-rate-panel",
    ]) {
      expect(screen.getByTestId(testid)).toBeInTheDocument();
    }
  });

  it("locks the control UI on a schema/policy-feature version mismatch (CG-G-S11a)", () => {
    const { sink, sent } = recordingSink();
    render(
      <InferenceScreen
        commandSink={sink}
        source={sourceWith({
          schema: {
            status: "MISMATCH",
            clientSchemaVersion: "1.4.0",
            serverSchemaVersion: "1.5.0",
            clientPolicyFeatureVersion: "gr00t-n1.5",
            serverPolicyFeatureVersion: "gr00t-n1.5",
            detail: "server schema newer than client",
          },
        })}
      />,
    );
    // The lock is visible, and every control affordance is disabled — so no start / mode /
    // task / takeover intent can reach a server that would reject it as INVALID_ARGUMENT.
    expect(screen.getByTestId("schema-lock-error")).toBeInTheDocument();
    expect(screen.getByTestId("control-locked-badge")).toBeInTheDocument();
    expect(screen.getByTestId("schema-negotiation")).toHaveAttribute("data-locked", "true");
    expect(screen.getByTestId("rollout-start")).toBeDisabled();
    expect(screen.getByTestId("takeover-btn")).toBeDisabled();
    expect(screen.getByTestId("form-option-LOCAL")).toBeDisabled();
    expect(screen.getByTestId("task-option-pick_place")).toBeDisabled();
    // The target selector emits a command frame too, so it is a control affordance and must
    // be locked as well — otherwise a select_target frame leaks past the lock to a server
    // that would reject it (the gap the audit caught).
    const targetButtons = screen.getAllByTestId(/^target-select-/);
    expect(targetButtons.length).toBeGreaterThan(0);
    for (const button of targetButtons) {
      expect(button).toBeDisabled();
    }
    // A disabled takeover control AND a disabled target selector both emit nothing when clicked.
    fireEvent.click(screen.getByTestId("takeover-btn"));
    fireEvent.click(targetButtons[0]);
    expect(sent.length).toBe(0);
  });

  it("shows the success rate with its Wilson CI, never a bare point estimate (CG-G-S11b)", () => {
    render(<InferenceScreen />);
    const rate = screen.getByTestId("success-rate");
    // The point estimate and BOTH Wilson bounds live in the one element — a reader cannot
    // see 65.0% without its ±width.
    expect(rate).toHaveTextContent("65.0%");
    expect(rate).toHaveTextContent("49.5%");
    expect(rate).toHaveTextContent("77.9%");
    expect(screen.queryByTestId("success-rate-pending")).toBeNull();
  });

  it("shows NO number during the 4B->4C landing window (2-landing note)", () => {
    render(<InferenceScreen source={sourceWith({ successRate: null })} />);
    expect(screen.getByTestId("success-rate-pending")).toBeInTheDocument();
    // No rate element at all — a placeholder number here would be a readable lie.
    expect(screen.queryByTestId("success-rate")).toBeNull();
    expect(screen.queryByTestId("success-rate-point")).toBeNull();
  });

  it("flags an N<20 report statistically meaningless and issues no ranking (CG-G-S11c)", () => {
    render(
      <InferenceScreen
        source={sourceWith({
          successRate: {
            rolloutSetId: "rollout_small",
            checkpoint: { outputDir: "outputs/train/x", step: 4000 },
            checkpointHash: "outputs/train/x@4000",
            nTrials: 5,
            nSuccess: 3,
            pointEstimate: 0.6,
            ciWilson95: { lower: 0.2307, upper: 0.8824, method: "wilson-95" },
            ciClopperPearson95: null,
            statisticallyMeaningful: false,
            seeds: [1, 2, 3, 4, 5],
            episodeLengthMedian: 190,
            collisionCount: 0,
            torqueLimitHits: 0,
            safetyStopCount: 0,
            inferenceLatencyP95: 40.0,
            failureTagCounts: { misreach: 2 },
            baselineKind: "self-baseline",
          },
        })}
      />,
    );
    expect(screen.getByTestId("meaningless-badge")).toHaveTextContent(STATISTICALLY_MEANINGLESS_LABEL);
    expect(screen.getByTestId("ranking-note")).toHaveAttribute("data-ranking-allowed", "false");
    // Even the meaningless report shows the CI beside the estimate (never bare).
    const rate = screen.getByTestId("success-rate");
    expect(rate).toHaveTextContent("60.0%");
    expect(rate).toHaveTextContent("23.1%");
    expect(rate).toHaveTextContent("88.2%");
  });

  it("starts LOCAL and ASYNC through the SAME start path (CG-G-S11e)", () => {
    const { sink, sent } = recordingSink();
    render(<InferenceScreen commandSink={sink} />);
    // Default is LOCAL/rtc → start emits start_rollout.
    fireEvent.click(screen.getByTestId("rollout-start"));
    // Switch to ASYNC (backend resolves to remote_grpc) → start emits start_rollout again.
    fireEvent.click(screen.getByTestId("form-option-ASYNC"));
    fireEvent.click(screen.getByTestId("rollout-start"));
    const starts = sent.filter((command) => command.op === "start_rollout");
    expect(starts.length).toBe(2);
    // Same op = same code path; the two differ ONLY in the deploymentForm field.
    expect(starts.every((command) => command.op === "start_rollout")).toBe(true);
    const forms = starts.map((command) => (command as { deploymentForm: string }).deploymentForm);
    expect(forms).toContain("LOCAL");
    expect(forms).toContain("ASYNC");
    const asyncStart = starts.find(
      (command) => (command as { deploymentForm: string }).deploymentForm === "ASYNC",
    ) as { backend: string };
    expect(asyncStart.backend).toBe("remote_grpc");
  });

  it("renders the action-queue size in real time from the live telemetry (CG-G-S11f)", () => {
    const { source, push } = controllableQueueSource({
      backend: "rtc",
      residualActions: 18,
      queueThreshold: 30,
      interpolatorResidual: 0,
      exhaustionCount: 0,
      tick: 100,
    });
    render(<InferenceScreen queueSource={source} />);
    expect(screen.getByTestId("action-queue")).toHaveAttribute("data-residual", "18");

    push({ backend: "rtc", residualActions: 7, queueThreshold: 30, interpolatorResidual: 0, exhaustionCount: 1, tick: 101 });
    expect(screen.getByTestId("action-queue")).toHaveAttribute("data-residual", "7");
    expect(screen.getByTestId("action-queue-residual")).toHaveTextContent("7");

    push({ backend: "rtc", residualActions: 30, queueThreshold: 30, interpolatorResidual: 0, exhaustionCount: 1, tick: 140 });
    expect(screen.getByTestId("action-queue")).toHaveAttribute("data-residual", "30");
  });

  it("blocks sync and offers RTC/async for the Orin+GR00T cell (CG-G-S11g, FR-INF-034)", () => {
    render(<InferenceScreen />);
    const syncOption = screen.getByTestId("backend-option-sync");
    expect(syncOption).toBeDisabled();
    expect(syncOption).toHaveAttribute("data-blocked", "true");
    expect(screen.getByTestId("backend-block-sync")).toHaveTextContent("FR-INF-034");
    // The non-sync alternative is live.
    expect(screen.getByTestId("backend-option-rtc")).not.toBeDisabled();
    expect(screen.getByTestId("required-alternatives")).toHaveTextContent("rtc");
  });

  it("blocks trt_full_pipeline for the Orin cell (CG-G-S11h, FR-INF-033)", () => {
    render(<InferenceScreen />);
    const trtFull = screen.getByTestId("opt-option-trt_full_pipeline");
    expect(trtFull).toBeDisabled();
    expect(trtFull).toHaveAttribute("data-blocked", "true");
    expect(screen.getByTestId("opt-block-trt_full_pipeline")).toHaveTextContent("FR-INF-033");
    // DiT-only tensorrt remains available.
    expect(screen.getByTestId("opt-option-tensorrt")).not.toBeDisabled();
  });

  it("renders a target as unsupported when its IK gate is fail_blocking (PG-IK-001)", () => {
    const base = defaultInferenceScreenData();
    render(
      <InferenceScreen
        source={sourceWith({
          fleetVerdicts: base.fleetVerdicts.map((verdict) =>
            verdict.target === "jetson_orin" ? { ...verdict, ikGate: "fail_blocking" } : verdict,
          ),
        })}
      />,
    );
    const support = screen.getByTestId("target-support-jetson_orin");
    expect(support).toHaveAttribute("data-support", "false");
    expect(support).toHaveTextContent("미지원");
  });

  it("disables start on a load-preflight refusal without recomputing it (WP-4B-03)", () => {
    const { sink, sent } = recordingSink();
    render(
      <InferenceScreen
        commandSink={sink}
        source={sourceWith({
          loadPreflight: {
            allowed: false,
            refusals: [
              {
                code: "GRIPPER_MIRROR",
                ruleId: "FR-INF-070",
                detail: "left gripper sign-mirror would silently invert the grasp",
                observed: "finger_joint2 mirrored",
                expected: "canonical sign",
              },
            ],
          },
        })}
      />,
    );
    expect(screen.getByTestId("rollout-start")).toBeDisabled();
    expect(screen.getByTestId("rollout-block-reasons")).toHaveTextContent("WP-4B-03");
    fireEvent.click(screen.getByTestId("rollout-start"));
    expect(sent.some((command) => command.op === "start_rollout")).toBe(false);
  });

  it("emits select_target / select_task / takeover intents", () => {
    const { sink, sent } = recordingSink();
    render(<InferenceScreen commandSink={sink} />);
    fireEvent.click(screen.getByTestId("target-select-rtx_5090"));
    fireEvent.click(screen.getByTestId("task-option-stack"));
    fireEvent.click(screen.getByTestId("takeover-btn"));
    expect(sent).toContainEqual({ op: "select_target", target: "rtx_5090" });
    expect(sent).toContainEqual({ op: "select_task", taskId: "stack" });
    expect(sent).toContainEqual({ op: "takeover" });
    // Takeover flips the rendered control holder.
    expect(screen.getByTestId("takeover-control")).toHaveAttribute("data-human-in-control", "true");
  });

  it("emits start_rollout carrying the resolved mode when startable", () => {
    const { sink, sent } = recordingSink();
    render(<InferenceScreen commandSink={sink} />);
    fireEvent.click(screen.getByTestId("rollout-start"));
    const start = sent.find((command) => command.op === "start_rollout");
    expect(start).toMatchObject({
      op: "start_rollout",
      deploymentForm: "LOCAL",
      backend: "rtc",
      policyId: "groot",
      taskId: "pick_place",
      target: "jetson_orin",
    });
  });
});
