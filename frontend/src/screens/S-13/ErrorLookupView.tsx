// Error-code lookup view (CG-G-S13f). The operator types an OA-* code; the view
// validates it against the frozen CTR-ERR grammar and resolves it in the
// backend-served registry. No code table lives here.

import { useState } from "react";

import { ErrorEntryCard } from "./ErrorEntryCard";
import { isLookupCandidate, lookupError } from "./errorLookup";
import type { ErrorRegistry } from "./types";

interface ErrorLookupViewProps {
  registry: ErrorRegistry;
}

export function ErrorLookupView({ registry }: ErrorLookupViewProps) {
  const [query, setQuery] = useState("");
  const trimmed = query.trim().toUpperCase();
  const candidate = trimmed.length > 0 && isLookupCandidate(trimmed);
  const entry = candidate ? lookupError(registry, trimmed) : null;

  return (
    <section className="oa-sys-view" aria-labelledby="oa-sys-errors-title" data-testid="error-lookup">
      <h2 id="oa-sys-errors-title" className="oa-sys-view__title">
        에러 코드 조회 — 정본 14 §2.10 (CTR-ERR)
      </h2>
      <label className="oa-sys-field">
        <span className="oa-sys-field__label">OA 코드</span>
        <input
          className="oa-sys-field__input"
          data-testid="error-query"
          type="text"
          value={query}
          placeholder="OA-CAN-001"
          onChange={(event) => setQuery(event.target.value)}
        />
      </label>

      {trimmed.length > 0 && !candidate && (
        <p className="oa-sys-alert" role="alert" data-testid="error-invalid">
          유효한 OA 코드 형식이 아닙니다.
        </p>
      )}
      {candidate && entry === null && (
        <p className="oa-sys-warn" role="status" data-testid="error-unknown">
          레지스트리에 없는 코드입니다: {trimmed}
        </p>
      )}
      {entry && <ErrorEntryCard entry={entry} />}
    </section>
  );
}
