// CG-G-S09a: the screen must never present an MJCF value as a hardware-spec basis.
// This panel is where the MJCF asset facts surface, and it frames them correctly:
// a standing disclaimer that the MuJoCo model is not a hardware-spec cross-check
// source, and a per-fact "sim asset, not a hardware spec" tag on every fact. The
// facts themselves come from simDomain, where their basis type has one inhabitant
// (`sim-asset-only`), so a hardware-spec attribution cannot be authored.

import {
  MJCF_ASSET_FACTS,
  MJCF_NOT_HARDWARE_SPEC_DISCLAIMER,
  SIM_ASSET_TAG,
} from "./simDomain";

export function AssetDisclaimer() {
  return (
    <section className="oa-sim__asset" aria-labelledby="oa-sim-asset-title">
      <h2 id="oa-sim-asset-title" className="oa-sim__section-title">
        시뮬레이션 자산
      </h2>
      <p className="oa-sim__asset-disclaimer" role="note">
        {MJCF_NOT_HARDWARE_SPEC_DISCLAIMER}
      </p>
      <ul className="oa-sim__asset-facts">
        {MJCF_ASSET_FACTS.map((fact) => (
          <li key={fact.id} className="oa-sim__asset-fact" data-basis={fact.basis}>
            <div className="oa-sim__asset-fact-head">
              <strong>{fact.label}</strong>
              <span className="oa-sim__asset-tag">{SIM_ASSET_TAG}</span>
            </div>
            <p className="oa-sim__asset-detail">{fact.detail}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
