// The inference-mode selector (CG-G-S11e/g/h). It offers the deployment form (LOCAL /
// ASYNC), the inference backend for that form, and the optimization path — disabling each
// option the active WP-4B-04 verdict blocks, with the backend's own reason and source. It
// recomputes nothing: `isBackendBlocked` / `isOptimizationBlocked` read the verdict, and
// LOCAL/ASYNC only pick which backends the form offers (the start itself is one path,
// resolved in screen.tsx). On a schema lock the whole selector is disabled.

import { DEPLOYMENT_FORMS, OPTIMIZATIONS } from "./types";
import type { DeploymentForm, InferenceBackend, InferenceModeConfig, Optimization, TargetPolicyVerdict } from "./types";
import {
  backendBlockReason,
  isBackendBlocked,
  isOptimizationBlocked,
  optimizationBlockReason,
} from "./deployVerdict";
import { backendsForForm } from "./rolloutMode";

export interface ModeSelectorViewProps {
  mode: InferenceModeConfig;
  verdict: TargetPolicyVerdict;
  disabled: boolean;
  onSetForm: (form: DeploymentForm) => void;
  onSetBackend: (backend: InferenceBackend) => void;
  onSetOptimization: (optimization: Optimization) => void;
}

const FORM_LABEL: Record<DeploymentForm, string> = {
  LOCAL: "LOCAL (인프로세스 sync/rtc)",
  ASYNC: "ASYNC (원격 gRPC)",
};

export function ModeSelectorView({
  mode,
  verdict,
  disabled,
  onSetForm,
  onSetBackend,
  onSetOptimization,
}: ModeSelectorViewProps) {
  const offeredBackends = backendsForForm(mode.deploymentForm);

  return (
    <section
      className="oa-inf__mode"
      aria-labelledby="oa-inf-mode-title"
      data-testid="mode-selector"
      data-disabled={disabled}
    >
      <h2 id="oa-inf-mode-title" className="oa-inf__section-title">
        추론 모드
      </h2>

      <fieldset className="oa-inf__fieldset" disabled={disabled}>
        <legend>배포 형태</legend>
        {DEPLOYMENT_FORMS.map((form) => (
          <label key={form} className="oa-inf__radio">
            <input
              type="radio"
              name="oa-inf-form"
              value={form}
              checked={mode.deploymentForm === form}
              data-testid={`form-option-${form}`}
              onChange={() => onSetForm(form)}
            />
            <span>{FORM_LABEL[form]}</span>
          </label>
        ))}
      </fieldset>

      <fieldset className="oa-inf__fieldset" disabled={disabled}>
        <legend>추론 백엔드</legend>
        {offeredBackends.map((backend) => {
          const blocked = isBackendBlocked(verdict, backend);
          const reason = backendBlockReason(verdict, backend);
          return (
            <div key={backend} className="oa-inf__option-row">
              <label className="oa-inf__radio">
                <input
                  type="radio"
                  name="oa-inf-backend"
                  value={backend}
                  checked={mode.backend === backend}
                  disabled={blocked}
                  data-testid={`backend-option-${backend}`}
                  data-blocked={blocked}
                  onChange={() => onSetBackend(backend)}
                />
                <span>{backend}</span>
              </label>
              {reason && (
                <p className="oa-inf__block-reason" data-testid={`backend-block-${backend}`}>
                  차단 ({reason.code}): {reason.rationale}
                  <span className="oa-inf__source"> — 출처: {reason.source}</span>
                </p>
              )}
            </div>
          );
        })}
        {verdict.requiredAlternatives.length > 0 && (
          <p className="oa-inf__alternatives" data-testid="required-alternatives">
            sync 차단 → 대안: {verdict.requiredAlternatives.join(" / ")}
          </p>
        )}
      </fieldset>

      <fieldset className="oa-inf__fieldset" disabled={disabled}>
        <legend>최적화 경로</legend>
        {OPTIMIZATIONS.map((optimization) => {
          const blocked = isOptimizationBlocked(verdict, optimization);
          const reason = optimizationBlockReason(verdict, optimization);
          return (
            <div key={optimization} className="oa-inf__option-row">
              <label className="oa-inf__radio">
                <input
                  type="radio"
                  name="oa-inf-opt"
                  value={optimization}
                  checked={mode.optimization === optimization}
                  disabled={blocked}
                  data-testid={`opt-option-${optimization}`}
                  data-blocked={blocked}
                  onChange={() => onSetOptimization(optimization)}
                />
                <span>{optimization}</span>
              </label>
              {reason && (
                <p className="oa-inf__block-reason" data-testid={`opt-block-${optimization}`}>
                  차단 ({reason.code}): {reason.rationale}
                  <span className="oa-inf__source"> — 출처: {reason.source}</span>
                </p>
              )}
            </div>
          );
        })}
      </fieldset>
    </section>
  );
}
