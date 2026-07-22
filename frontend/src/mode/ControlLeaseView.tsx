// The control-lease state view (FR-GUI-092, U-4). Shows the lease fields, whether
// it is active or expired, whether this client is controlling or an observer, the
// standing dead-man margin (remaining time), and the last reject reason from
// anti-replay classification. The dead-man margin is shown even when healthy so a
// coming auto-hold is visible before it happens — the view surfaces the lease, it
// renews nothing (renewal is the WS client's job, WP-G-01).

import {
  isLeaseActive,
  leaseRemaining,
  type ControlLease,
  type LeaseClock,
  type LeaseVerdict,
} from "./lease";
import { ROLE_LABELS, mayHoldControl, type LeaseRole } from "./roles";

export interface ControlLeaseViewProps {
  lease: ControlLease | null;
  clock: LeaseClock;
  role: LeaseRole;
  // The last anti-replay verdict, shown when a frame was refused (CG-G-04d).
  lastVerdict: LeaseVerdict | null;
}

const VERDICT_LABELS: Readonly<Record<LeaseVerdict, string>> = {
  accepted: "수락됨",
  rejected_expired: "거부: 만료된 lease",
  rejected_stale_generation: "거부: 낡은 generation (탈취 시도)",
  rejected_replay: "거부: 시퀀스 역행/중복 재생",
  discarded_aged: "폐기: 만료된 age 창",
};

export function ControlLeaseView({ lease, clock, role, lastVerdict }: ControlLeaseViewProps) {
  const active = lease !== null && isLeaseActive(lease, clock);
  // Controlling requires an active lease AND a role that may hold control; an
  // observer never renders as controlling even if a lease is present.
  const controlling = active && mayHoldControl(role);
  return (
    <section className="oa-lease" aria-label="제어권 lease 상태">
      <p className="oa-lease__role">역할: {ROLE_LABELS[role]}</p>
      <p className="oa-lease__authority" data-controlling={controlling}>
        {controlling ? "제어권 보유 (controlling)" : "관찰자 / 권리 없음 (observer)"}
      </p>
      {lease !== null ? (
        <dl className="oa-lease__fields">
          <dt>session_id</dt>
          <dd>{lease.sessionId}</dd>
          <dt>lease_generation</dt>
          <dd>{lease.leaseGeneration}</dd>
          <dt>sequence</dt>
          <dd>{lease.sequence}</dd>
          <dt>상태</dt>
          <dd data-active={active}>{active ? "활성" : "만료"}</dd>
          <dt>데드맨 잔여</dt>
          <dd className="oa-lease__remaining">{leaseRemaining(lease, clock)} ms</dd>
        </dl>
      ) : (
        <p className="oa-lease__empty">보유 lease 없음</p>
      )}
      {lastVerdict !== null && lastVerdict !== "accepted" ? (
        <p className="oa-lease__verdict" role="alert">
          {VERDICT_LABELS[lastVerdict]}
        </p>
      ) : null}
    </section>
  );
}
