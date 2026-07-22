// The WP-3C gate panel. PG-STO-001 (storage integrity, WP-3C-02) and the interlock
// (WP-3C-06) and crash/resume (WP-3C-07) gates are HARDWARE gates that are not built
// yet, so their verdict arrives as `pending`/`unavailable`. This panel renders that
// state honestly — a muted pending/reduced badge — and the screen NEVER fabricates a
// verdict for a gate that has not landed nor blocks the collection on one. A gate
// that later lands DEGRADED_ACCEPTED renders as a reduced badge, not a failure.

import type { GateState, GateStatus } from "./types";

export interface GateStatusViewProps {
  gates: readonly GateStatus[];
}

const STATE_LABELS: Record<GateState, string> = {
  pending: "대기 (미착지)",
  unavailable: "미가용",
  degraded_accepted: "축소 수용",
  pass: "통과",
  fail: "실패",
};

export function GateStatusView({ gates }: GateStatusViewProps) {
  return (
    <section className="oa-collect__gates" aria-labelledby="oa-collect-gates-title">
      <h2 id="oa-collect-gates-title" className="oa-collect__section-title">
        3C 게이트 상태
      </h2>
      <ul className="oa-collect__gate-list">
        {gates.map((gate) => (
          <li key={gate.id} className="oa-collect__gate-row" data-testid={`gate-${gate.id}`}>
            <span className="oa-collect__gate-id">{gate.id}</span>
            <span className="oa-collect__gate-label">{gate.label}</span>
            <span
              className={`oa-collect__gate-state oa-collect__gate-state--${gate.state}`}
              data-state={gate.state}
              role="status"
            >
              {STATE_LABELS[gate.state]}
            </span>
            {gate.detail && <span className="oa-collect__gate-detail">{gate.detail}</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}
