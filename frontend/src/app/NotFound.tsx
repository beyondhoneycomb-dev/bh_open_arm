// Catch-all for a path outside the frozen route set. It is not a screen and is
// excluded from the 13 §2.6 inventory; it exists only so an unknown URL fails
// visibly instead of rendering blank.

import { Link } from "react-router-dom";

export function NotFound() {
  return (
    <section className="oa-scaffold" aria-labelledby="oa-notfound-title">
      <h1 id="oa-notfound-title" className="oa-scaffold__title">
        경로 없음 (404)
      </h1>
      <p className="oa-scaffold__pending">
        <Link to="/">대시보드로</Link>
      </p>
    </section>
  );
}
