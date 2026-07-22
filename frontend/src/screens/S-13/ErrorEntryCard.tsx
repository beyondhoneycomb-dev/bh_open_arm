// Renders one frozen-registry error entry as {severity, cause, recovery, doc
// link} (CG-G-S13f). Every field is read straight from the backend-served
// ErrorRegistryEntry; the doc link is a same-origin relative path into the spec.

import { severityName } from "./errorLookup";
import type { ErrorRegistryEntry } from "./types";

interface ErrorEntryCardProps {
  entry: ErrorRegistryEntry;
}

export function ErrorEntryCard({ entry }: ErrorEntryCardProps) {
  const severity = severityName(entry);
  return (
    <article
      className="oa-sys-error"
      data-testid={`error-entry-${entry.code}`}
      data-code={entry.code}
      data-severity={severity ?? "UNKNOWN"}
    >
      <header className="oa-sys-error__head">
        <span className="oa-sys-error__code">{entry.code}</span>
        <span className="oa-sys-error__sev" data-testid="error-severity">
          {severity ?? `severity ${entry.severity}`}
        </span>
      </header>
      <dl className="oa-sys-error__fields">
        <dt>원인</dt>
        <dd data-testid="error-cause">
          {entry.messageKo} ({entry.messageEn})
        </dd>
        <dt>복구 절차</dt>
        <dd data-testid="error-recovery">{entry.recoveryHint}</dd>
        <dt>문서</dt>
        <dd>
          <a className="oa-sys-error__doc" data-testid="error-doc" href={entry.docUrl}>
            {entry.docUrl}
          </a>
        </dd>
      </dl>
    </article>
  );
}
