// Inference-screen command intents (WP-G-S11). The screen is a FACADE: it SENDS operator
// intent to the backend-owned inference engine (WP-4B-*) and performs no transformation
// itself. One invariant is structural in the op set below:
//
//   - LOCAL and ASYNC resolve to ONE start path (CG-G-S11e): the sole start op is
//     `start_rollout`, and it carries the `deploymentForm` as a FIELD. There is no
//     form-specific start op — a LOCAL rollout and an ASYNC rollout are the same command
//     with a different field value, so both go through the single gated emit site in
//     screen.tsx. The static check proves exactly one start op exists and exactly one emit
//     site sends it (staticChecks.test.ts), the way S-10 proves `create_job` is singular.
//
// The screen never spawns a CLI per mode (11 §2.5 — a per-mode CLI would re-zero the arm
// on every switch); it sends intent and the backend embeds the engine.

import type {
  DeploymentForm,
  DeploymentTarget,
  InferenceBackend,
  Optimization,
} from "./types";

// Start a rollout. The ONE start op — LOCAL and ASYNC differ only in `deploymentForm`
// (CG-G-S11e). Carries the full resolved mode so the backend needs no second lookup.
export interface StartRolloutCommand {
  op: "start_rollout";
  deploymentForm: DeploymentForm;
  backend: InferenceBackend;
  optimization: Optimization;
  policyId: string;
  taskId: string;
  target: DeploymentTarget;
}

// Stop the active rollout (returns to initial position on the LOCAL path).
export interface StopRolloutCommand {
  op: "stop_rollout";
}

// Set the inference mode without starting (config-only intent).
export interface SetModeCommand {
  op: "set_mode";
  deploymentForm: DeploymentForm;
  backend: InferenceBackend;
  optimization: Optimization;
}

// Select which deployment target the block-matrix verdict is shown for.
export interface SelectTargetCommand {
  op: "select_target";
  target: DeploymentTarget;
}

// Select the active language task (RolloutConfig.task).
export interface SelectTaskCommand {
  op: "select_task";
  taskId: string;
}

// A human takes control mid-rollout (FR-INF-048), and hands it back.
export interface TakeoverCommand {
  op: "takeover";
}

export interface ReleaseTakeoverCommand {
  op: "release_takeover";
}

export type InferenceCommand =
  | StartRolloutCommand
  | StopRolloutCommand
  | SetModeCommand
  | SelectTargetCommand
  | SelectTaskCommand
  | TakeoverCommand
  | ReleaseTakeoverCommand;

// The sink a screen publishes intents to. In production this wraps the single WS client's
// control-frame send (WP-G-01), where the server accepts or refuses by lease/role — the
// browser never decides. The default is a no-op so the AI-offline lane drives the screen
// without a backend.
export interface InferenceCommandSink {
  send(command: InferenceCommand): void;
}

export const noopCommandSink: InferenceCommandSink = {
  send: () => {},
};

// Project a command intent onto the frozen CTR-WS command frame body. Kept separate from
// the sink so the wire shape is testable without a socket.
export function commandToWire(command: InferenceCommand): Record<string, unknown> {
  return { type: "command", ...command };
}
