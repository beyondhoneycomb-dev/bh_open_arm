// The single rollout-start path (CG-G-S11e). LOCAL and ASYNC are two deployment forms of
// the SAME engine call (11 §2.5 / FR-INF-021: in-process sync/rtc vs remote gRPC), and the
// backend factory (`build_inference_engine`) is one entry point for all three backends. On
// the screen this means: whichever form the operator picks, the start intent is built by
// the ONE `buildStartRollout` function below and emitted by the ONE gated site in
// screen.tsx. The form is a field, not a fork — there is no second, form-specific start
// path a static check would find.

import type { StartRolloutCommand } from "./commands";
import type {
  DeploymentForm,
  DeploymentTarget,
  InferenceBackend,
  InferenceModeConfig,
  Optimization,
  TargetPolicyVerdict,
} from "./types";
import { isBackendBlocked } from "./deployVerdict";

// The backends a deployment form offers (11 §2.5). LOCAL is the in-process rollout engine
// (sync/rtc); ASYNC is the remote gRPC path (remote_grpc). This constrains the backend
// options a form exposes; the verdict then blocks specific backends within that set.
export function backendsForForm(form: DeploymentForm): InferenceBackend[] {
  return form === "LOCAL" ? ["sync", "rtc"] : ["remote_grpc"];
}

// The backend to select when a form is (re)chosen: the first backend the form offers that
// the active verdict does not block. On Jetson Orin + GR00T, LOCAL's `sync` is blocked
// (FR-INF-034), so LOCAL resolves to `rtc` — the operator never lands on a blocked default.
export function defaultBackendForForm(
  form: DeploymentForm,
  verdict: TargetPolicyVerdict,
): InferenceBackend {
  const offered = backendsForForm(form);
  return offered.find((backend) => !isBackendBlocked(verdict, backend)) ?? offered[0];
}

// The inputs the one start builder needs, gathered so LOCAL and ASYNC pass the same shape.
export interface StartRolloutInput {
  mode: InferenceModeConfig;
  policyId: string;
  taskId: string;
  target: DeploymentTarget;
}

// The ONE rollout-start command builder both forms resolve to (CG-G-S11e). LOCAL and ASYNC
// differ only in `mode.deploymentForm`; every other field is built identically here, so the
// two selections produce the same command shape through the same path.
export function buildStartRollout(input: StartRolloutInput): StartRolloutCommand {
  return {
    op: "start_rollout",
    deploymentForm: input.mode.deploymentForm,
    backend: input.mode.backend,
    optimization: input.mode.optimization,
    policyId: input.policyId,
    taskId: input.taskId,
    target: input.target,
  };
}

// Whether a chosen backend is valid for its form and unblocked by the verdict — the guard
// the single emit site checks before sending, so a start never goes out on a blocked cell.
export function isModeStartable(
  mode: InferenceModeConfig,
  verdict: TargetPolicyVerdict,
): boolean {
  const formOffersBackend = backendsForForm(mode.deploymentForm).includes(mode.backend);
  const backendOpen = !isBackendBlocked(verdict, mode.backend);
  const optimizationOpen = !verdict.blockedOptimizations.includes(mode.optimization);
  return formOffersBackend && backendOpen && optimizationOpen;
}

// Re-exported so callers name the optimization type without a second import path.
export type { Optimization };
