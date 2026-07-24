// The policy selector + hyperparameter form (FR-GUI-121, CG-G-S10a/e/g). The policy
// list is rendered from `options` — data derived at runtime from the installed lerobot
// registry (policyRegistry.ts); no policy name is written in this component. A blocked
// policy is shown, disabled, with its located reason AND the source of the ceiling it
// exceeded (the WP-4B-01 three-axis matrix result) so an operator can act on it; a
// policy the backend marked unavailable (vqbet) is shown blocked with its reason. Each
// hyperparameter field shows its CLI flag beside the label so the GUI form and the CLI
// read as one system; optimizer/scheduler fields are grouped because overriding one
// requires re-supplying the group (the backend rejects a half-overridden preset).

import type { HyperparamField, PolicyOption } from "./types";

export interface PolicyFormViewProps {
  options: readonly PolicyOption[];
  selectedPolicyId: string;
  lerobotVersion: string;
  hyperparams: readonly HyperparamField[];
  onSelectPolicy: (policyId: string) => void;
  onSetHyperparam: (key: string, value: string) => void;
}

const GROUP_LABEL: Readonly<Record<HyperparamField["group"], string>> = {
  core: "핵심",
  optimizer: "옵티마이저 (그룹 · 하나 덮어쓰면 전체 재지정)",
  scheduler: "스케줄러 (그룹 · 하나 덮어쓰면 전체 재지정)",
};

const GROUP_ORDER: readonly HyperparamField["group"][] = ["core", "optimizer", "scheduler"];

export function PolicyFormView({
  options,
  selectedPolicyId,
  lerobotVersion,
  hyperparams,
  onSelectPolicy,
  onSetHyperparam,
}: PolicyFormViewProps) {
  return (
    <section className="oa-trn__panel" aria-labelledby="oa-trn-policy-title" data-testid="policy-form">
      <h2 id="oa-trn-policy-title" className="oa-trn__section-title">
        정책 선택 + 하이퍼파라미터
      </h2>

      <p className="oa-trn__provenance" data-testid="policy-provenance">
        정책 목록은 설치된 LeRobot {lerobotVersion} 레지스트리에서 런타임 유도됨 (하드코딩 아님)
      </p>

      <ul className="oa-trn__policy-list" role="radiogroup" aria-label="정책">
        {options.map((option) => {
          const id = option.capability.id;
          const selected = id === selectedPolicyId;
          return (
            <li key={id} className="oa-trn__policy-item">
              <label
                className="oa-trn__policy-label"
                data-testid={`policy-${id}`}
                data-blocked={option.blocked}
              >
                <input
                  type="radio"
                  name="oa-trn-policy"
                  value={id}
                  checked={selected && !option.blocked}
                  disabled={option.blocked}
                  data-testid={`policy-radio-${id}`}
                  onChange={() => onSelectPolicy(id)}
                />
                <span className="oa-trn__policy-name">{id}</span>
                <span className="oa-trn__muted"> ({option.capability.configClass})</span>
                {option.blocked && (
                  <span className="oa-trn__badge oa-trn__badge--blocked" data-testid={`policy-blocked-${id}`}>
                    차단됨
                  </span>
                )}
              </label>

              {option.blocked && option.blockReason !== null && (
                <p className="oa-trn__block-reason" data-testid={`policy-reason-${id}`}>
                  <span>{option.blockReason.human}</span>
                  <span className="oa-trn__source" data-testid={`policy-source-${id}`}>
                    출처: {option.blockReason.source}
                  </span>
                </p>
              )}
            </li>
          );
        })}
      </ul>

      <div className="oa-trn__hyperparams">
        {GROUP_ORDER.map((group) => {
          const fields = hyperparams.filter((field) => field.group === group);
          if (fields.length === 0) {
            return null;
          }
          return (
            <fieldset key={group} className="oa-trn__hp-group" data-testid={`hp-group-${group}`}>
              <legend>{GROUP_LABEL[group]}</legend>
              {fields.map((field) => (
                <label key={field.key} className="oa-trn__field">
                  <span>
                    {field.label}
                    <code className="oa-trn__flag">{field.cliFlag}</code>
                  </span>
                  <input
                    type="text"
                    value={field.value}
                    data-testid={`hp-${field.key}`}
                    onChange={(event) => onSetHyperparam(field.key, event.target.value)}
                  />
                </label>
              ))}
            </fieldset>
          );
        })}
      </div>
    </section>
  );
}
