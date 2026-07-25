// Inference/eval screen (WP-G-S11, route /inference). A FACADE over the INF domain (11): it
// renders the Wave 4B/4C backend's inference surface — the schema negotiation, the inference
// loop, the action queue, the mode selector, the task switcher, the takeover control, the
// rollout control, the per-target block matrix, and (the 4C increment) the success-rate
// panel — and emits operator intent. It owns no evaluation logic: the policy/compat/load/
// deploy verdicts and the success-rate report are the backend's, and the screen recomputes
// none of them (02d §2.2, WP-4B-01..04 + WP-4C-03).
//
// Two rules this screen enforces itself, both as single gates:
//   - the SCHEMA LOCK (schemaGate.ts): the server is the schema authority, so on a reported
//     version MISMATCH every control affordance is disabled and a clear error is shown,
//     before any start/mode/task/takeover intent can reach a server that would reject it
//     with INVALID_ARGUMENT (CG-G-S11a).
//   - the SINGLE START PATH (rolloutMode.ts): LOCAL and ASYNC resolve to one gated
//     `buildStartRollout` emit site, so a rollout starts through exactly one code path
//     regardless of deployment form (CG-G-S11e), and only past every blocker.
// Like the sibling screens it renders from a `source` prop with an offline default fixture
// and a no-op `commandSink`, opens no socket and offers no reconnect (invariant I-2). The
// action-queue size binds to a live telemetry seam so it re-renders in real time (CG-G-S11f).

import { useEffect, useMemo, useState } from "react";

import "./inference.css";
import { ActionQueueView } from "./ActionQueueView";
import { DeployMatrixView } from "./DeployMatrixView";
import { InferenceLoopView } from "./InferenceLoopView";
import { ModeSelectorView } from "./ModeSelectorView";
import { RolloutControlView } from "./RolloutControlView";
import { SchemaNegotiationView } from "./SchemaNegotiationView";
import { SuccessRatePanelView } from "./SuccessRatePanelView";
import { TakeoverControlView } from "./TakeoverControlView";
import { TaskSwitcherView } from "./TaskSwitcherView";
import { controlLockReasons } from "./schemaGate";
import { buildStartRollout, defaultBackendForForm, isModeStartable } from "./rolloutMode";
import { describeSuccessRate } from "./successRate";
import { defaultInferenceSource } from "./inferenceSource";
import { noopCommandSink, type InferenceCommandSink } from "./commands";
import type {
  ActionQueueTelemetry,
  DeploymentForm,
  DeploymentTarget,
  InferenceBackend,
  InferenceDataSource,
  InferenceModeConfig,
  Optimization,
  QueueTelemetrySource,
  TargetPolicyVerdict,
} from "./types";

export interface InferenceScreenProps {
  source?: InferenceDataSource;
  commandSink?: InferenceCommandSink;
  queueSource?: QueueTelemetrySource;
}

const DEFAULT_SOURCE: InferenceDataSource = defaultInferenceSource();

// The loop phases in which a rollout is live (so the stop control is enabled).
const LIVE_PHASES = ["WARMUP", "RUNNING", "PAUSED", "TAKEOVER", "RETURNING"];

export default function InferenceScreen({
  source,
  commandSink = noopCommandSink,
  queueSource,
}: InferenceScreenProps) {
  const resolved = source ?? DEFAULT_SOURCE;
  const data = useMemo(() => resolved.load(), [resolved]);

  const [mode, setMode] = useState<InferenceModeConfig>(data.mode);
  const [selectedTarget, setSelectedTarget] = useState<DeploymentTarget>(data.selectedTarget);
  const [activeTaskId, setActiveTaskId] = useState(
    (data.tasks.find((task) => task.active) ?? data.tasks[0]).id,
  );
  const [humanInControl, setHumanInControl] = useState(data.takeover.humanInControl);
  const [queue, setQueue] = useState<ActionQueueTelemetry>(
    () => (queueSource ? queueSource.initial() : data.queue),
  );

  // The action-queue size is bound to the live telemetry stream: each frame the source
  // pushes re-renders the size (CG-G-S11f). The offline default pushes nothing; a test
  // drives frames to prove the binding is live, not baked at load.
  useEffect(() => {
    if (!queueSource) {
      return;
    }
    return queueSource.subscribe(setQueue);
  }, [queueSource]);

  // The active WP-4B-04 verdict is the fleet verdict for the selected target — read, not
  // recomputed. Changing target changes which cell the mode selector gates against.
  const activeVerdict: TargetPolicyVerdict =
    data.fleetVerdicts.find((verdict) => verdict.target === selectedTarget) ?? data.fleetVerdicts[0];

  const lockReasons = controlLockReasons(data.schema);
  const locked = lockReasons.length > 0;

  const takeover = { ...data.takeover, humanInControl };
  const running = LIVE_PHASES.includes(data.loop.phase);

  // Every reason a rollout cannot start, composed from the backend verdicts (the screen
  // decides none of them). Empty means startable.
  const rolloutBlockReasons = useMemo(() => {
    const reasons: string[] = [];
    if (locked) {
      reasons.push("스키마/policy feature 버전 불일치로 제어가 잠김 (CG-G-S11a)");
    }
    if (!isModeStartable(mode, activeVerdict)) {
      reasons.push(
        `선택한 모드(${mode.deploymentForm}/${mode.backend}/${mode.optimization})가 ` +
          `${selectedTarget}에서 차단됨 — WP-4B-04 verdict`,
      );
    }
    if (!data.policyCompat.allowed) {
      const first = data.policyCompat.blockingReasons[0];
      reasons.push(`정책 비호환 (WP-4B-01): ${first ? first.message : "구조적으로 사용 불가"}`);
    }
    if (!data.checkpointDataset.allowed) {
      const first = data.checkpointDataset.reasons[0];
      reasons.push(`체크포인트↔데이터셋 불일치 (WP-4B-02): ${first ? first.detail : "OA-DAT-002"}`);
    }
    if (!data.loadPreflight.allowed) {
      const first = data.loadPreflight.refusals[0];
      reasons.push(`로드 프리플라이트 거부 (WP-4B-03): ${first ? first.detail : "load refused"}`);
    }
    if (activeTaskId === "") {
      reasons.push("태스크가 선택되지 않았습니다");
    }
    return reasons;
  }, [locked, mode, activeVerdict, selectedTarget, data, activeTaskId]);

  const canStart = rolloutBlockReasons.length === 0;
  const successDisplay = describeSuccessRate(data.successRate);

  function changeForm(form: DeploymentForm): void {
    const backend = defaultBackendForForm(form, activeVerdict);
    const next: InferenceModeConfig = { ...mode, deploymentForm: form, backend };
    setMode(next);
    commandSink.send({ op: "set_mode", ...next });
  }

  function changeBackend(backend: InferenceBackend): void {
    const next: InferenceModeConfig = { ...mode, backend };
    setMode(next);
    commandSink.send({ op: "set_mode", ...next });
  }

  function changeOptimization(optimization: Optimization): void {
    const next: InferenceModeConfig = { ...mode, optimization };
    setMode(next);
    commandSink.send({ op: "set_mode", ...next });
  }

  function selectTarget(target: DeploymentTarget): void {
    if (locked) {
      return;
    }
    setSelectedTarget(target);
    commandSink.send({ op: "select_target", target });
  }

  function selectTask(taskId: string): void {
    if (locked) {
      return;
    }
    setActiveTaskId(taskId);
    commandSink.send({ op: "select_task", taskId });
  }

  function takeControl(): void {
    if (locked) {
      return;
    }
    setHumanInControl(true);
    commandSink.send({ op: "takeover" });
  }

  function releaseControl(): void {
    if (locked) {
      return;
    }
    setHumanInControl(false);
    commandSink.send({ op: "release_takeover" });
  }

  function stopRollout(): void {
    commandSink.send({ op: "stop_rollout" });
  }

  // The SINGLE start_rollout emit site (CG-G-S11e). LOCAL and ASYNC both reach here; the
  // form is a field of the one command `buildStartRollout` makes. The gate precedes the
  // emit, so no start goes out while any blocker stands.
  function emitStartRollout(): void {
    if (!canStart) {
      return;
    }
    commandSink.send(
      buildStartRollout({
        mode,
        policyId: data.policyId,
        taskId: activeTaskId,
        target: selectedTarget,
      }),
    );
  }

  return (
    <div className="oa-inf" data-screen="S-11">
      <header className="oa-inf__head">
        <p className="oa-inf__id">/inference</p>
        <h1 className="oa-inf__title">추론/평가</h1>
        {locked && (
          <p className="oa-inf__badge oa-inf__badge--locked" data-testid="control-locked-badge">
            제어 잠김 — 스키마 버전 불일치
          </p>
        )}
      </header>

      <SchemaNegotiationView schema={data.schema} locked={locked} lockReasons={lockReasons} />

      <div className="oa-inf__loop-row">
        <InferenceLoopView loop={data.loop} policyId={data.policyId} />
        <ActionQueueView telemetry={queue} />
      </div>

      <DeployMatrixView
        fleetVerdicts={data.fleetVerdicts}
        selectedTarget={selectedTarget}
        onSelectTarget={selectTarget}
        disabled={locked}
      />

      <div className="oa-inf__control-row">
        <ModeSelectorView
          mode={mode}
          verdict={activeVerdict}
          disabled={locked}
          onSetForm={changeForm}
          onSetBackend={changeBackend}
          onSetOptimization={changeOptimization}
        />
        <TaskSwitcherView
          tasks={data.tasks}
          activeTaskId={activeTaskId}
          disabled={locked}
          onSelectTask={selectTask}
        />
      </div>

      <div className="oa-inf__control-row">
        <TakeoverControlView
          takeover={takeover}
          disabled={locked}
          onTakeover={takeControl}
          onRelease={releaseControl}
        />
        <RolloutControlView
          canStart={canStart}
          blockReasons={rolloutBlockReasons}
          running={running}
          onStart={emitStartRollout}
          onStop={stopRollout}
        />
      </div>

      <SuccessRatePanelView display={successDisplay} report={data.successRate} />
    </div>
  );
}
