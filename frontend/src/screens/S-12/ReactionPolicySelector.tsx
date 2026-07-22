// The reaction-policy selector. It renders the six SAF policies (FR-SAF-037),
// pre-selects the backend's current mode — or the safe default STOP_HOLD when the
// backend has reported none — and emits the operator's choice as an intent the
// backend applies. The default is never the power-cut policy (CG-G-S12a). Policies
// that drop the load are tagged, because on a brakeless arm that is the one fact
// the operator must not misread.

import {
  REACTION_MODES,
  REACTION_MODE_SPECS,
  reactionDropsLoad,
  resolveSelectedReaction,
  type ReactionMode,
} from "./reactionPolicy";

interface ReactionPolicySelectorProps {
  // The reaction the backend currently applies, or null if none reported.
  backendMode: ReactionMode | null;
  onSelectReaction: (mode: ReactionMode) => void;
}

export function ReactionPolicySelector({
  backendMode,
  onSelectReaction,
}: ReactionPolicySelectorProps) {
  const selected = resolveSelectedReaction(backendMode);

  return (
    <section className="oa-safety__panel" aria-labelledby="oa-safety-reaction-title">
      <h2 id="oa-safety-reaction-title" className="oa-safety__panel-title">
        반응 정책
      </h2>

      <fieldset style={{ border: "none", margin: 0, padding: 0 }}>
        <legend className="oa-safety__status-line">
          충돌 시 반응 · 기본 <b>STOP_HOLD</b> (전원 유지, 낙하 없음)
        </legend>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {REACTION_MODES.map((mode) => {
            const spec = REACTION_MODE_SPECS[mode];
            const drops = reactionDropsLoad(mode);
            const isSelected = selected === mode;
            const className = [
              "oa-reaction__option",
              isSelected ? "oa-reaction__option--selected" : "",
              drops ? "oa-reaction__option--drop" : "",
            ]
              .filter(Boolean)
              .join(" ");
            return (
              <label key={mode} className={className} data-reaction-option={mode}>
                <input
                  type="radio"
                  name="oa-safety-reaction"
                  value={mode}
                  checked={isSelected}
                  onChange={() => onSelectReaction(mode)}
                />
                <span>
                  <span className="oa-reaction__label">{spec.label}</span>
                  <br />
                  <span className="oa-reaction__effect">{spec.effect}</span>
                </span>
                {drops && (
                  <span className="oa-reaction__drop-tag" data-drop-warning={mode}>
                    낙하 위험
                  </span>
                )}
              </label>
            );
          })}
        </div>
      </fieldset>
    </section>
  );
}
