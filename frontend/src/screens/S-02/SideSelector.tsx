// The side-selection control (CG-G-S02a). With no side chosen the backend locks
// every joint to a ±5° band and clips silently — so this control is the operator's
// only signal that a missing side, not a good limit, is why the arm will not move.
// It renders the standing warning while unchosen and reports the choice upward; it
// does not clamp anything.

import { SIDE_UNSET_LOCK_WARNING } from "./constants";
import { ARM_SIDES, ARM_SIDE_LABELS, canProceedWithSide, type SideSelection } from "./sideSelection";

interface SideSelectorProps {
  side: SideSelection;
  onSelect: (side: SideSelection) => void;
}

export function SideSelector({ side, onSelect }: SideSelectorProps) {
  const chosen = canProceedWithSide(side);
  return (
    <section className="oa-s02-side" aria-labelledby="oa-s02-side-title" data-panel="side">
      <h2 id="oa-s02-side-title" className="oa-s02__panel-title">
        팔 선택 (side)
      </h2>

      <fieldset className="oa-s02-side__choices">
        <legend>side를 선택하세요 (강제)</legend>
        {ARM_SIDES.map((candidate) => (
          <label key={candidate}>
            <input
              type="radio"
              name="oa-s02-side"
              value={candidate}
              checked={side === candidate}
              onChange={() => onSelect(candidate)}
            />
            {ARM_SIDE_LABELS[candidate]}
          </label>
        ))}
      </fieldset>

      {!chosen && (
        <p className="oa-s02-side__warning" role="alert" data-warning="side-unset">
          {SIDE_UNSET_LOCK_WARNING}
        </p>
      )}
    </section>
  );
}
