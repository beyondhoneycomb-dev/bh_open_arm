// Placeholder a route renders until its screen WP (WP-G-S01..S13) lands. It is
// deliberately inert — no robot control, no backend writes — but it does surface
// the screen's identity and lets the operator query which domain specification
// the screen implements (CG-G-00c). "Not yet implemented" is shown honestly
// rather than an empty page that could read as "nothing is wrong".

import { domainSpecsForScreen } from "../routes/registry";
import type { ScreenDescriptor } from "../routes/registry";

interface ScreenScaffoldProps {
  screen: ScreenDescriptor;
}

export function ScreenScaffold({ screen }: ScreenScaffoldProps) {
  const specs = domainSpecsForScreen(screen.id);
  return (
    <section className="oa-scaffold" aria-labelledby="oa-scaffold-title">
      <header className="oa-scaffold__head">
        <p className="oa-scaffold__id">{screen.id}</p>
        <h1 id="oa-scaffold-title" className="oa-scaffold__title">
          {screen.title}
        </h1>
      </header>
      <p className="oa-scaffold__pending" role="status">
        화면 미구현 — 담당 WP 착지 대기 (not yet implemented)
      </p>
      <div className="oa-scaffold__spec">
        <h2 className="oa-scaffold__spec-title">도메인 명세</h2>
        <ul className="oa-scaffold__spec-list">
          {specs.map((spec) => (
            <li key={spec.code}>
              <a href={spec.specUrl} className="oa-scaffold__spec-link">
                {spec.code} · {spec.doc} {spec.title}
              </a>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
