// The schema / policy-feature version negotiation view (CG-G-S11a). It renders the
// server-reported versions and, on a MISMATCH, a prominent lock error — the server is the
// schema authority and would reject with INVALID_ARGUMENT, so the screen locks its control
// UI first. This view only DISPLAYS the negotiation and the lock reasons the gate composed;
// it decides nothing.

import type { SchemaNegotiation } from "./types";

export interface SchemaNegotiationViewProps {
  schema: SchemaNegotiation;
  locked: boolean;
  lockReasons: readonly string[];
}

export function SchemaNegotiationView({ schema, locked, lockReasons }: SchemaNegotiationViewProps) {
  return (
    <section
      className="oa-inf__schema"
      aria-labelledby="oa-inf-schema-title"
      data-testid="schema-negotiation"
      data-locked={locked}
    >
      <h2 id="oa-inf-schema-title" className="oa-inf__section-title">
        스키마 협상
      </h2>

      {locked && (
        <div className="oa-inf__lock-error" role="alert" data-testid="schema-lock-error">
          <strong>추론 제어 UI 잠금</strong>
          <ul className="oa-inf__lock-reasons">
            {lockReasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      )}

      <dl className="oa-inf__schema-grid">
        <div className="oa-inf__schema-row" data-match={schema.clientSchemaVersion === schema.serverSchemaVersion}>
          <dt>스키마 버전</dt>
          <dd>
            클라이언트 <code>{schema.clientSchemaVersion}</code> · 서버{" "}
            <code data-testid="server-schema-version">{schema.serverSchemaVersion}</code>
          </dd>
        </div>
        <div
          className="oa-inf__schema-row"
          data-match={schema.clientPolicyFeatureVersion === schema.serverPolicyFeatureVersion}
        >
          <dt>policy feature 버전</dt>
          <dd>
            클라이언트 <code>{schema.clientPolicyFeatureVersion}</code> · 서버{" "}
            <code data-testid="server-feature-version">{schema.serverPolicyFeatureVersion}</code>
          </dd>
        </div>
      </dl>
    </section>
  );
}
