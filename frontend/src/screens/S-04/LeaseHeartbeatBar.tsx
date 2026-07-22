// Lease-remaining + heartbeat-margin bar (CG-G-S04d). Both are shown ALWAYS —
// unconditionally rendered, never behind a mode or a hover — because if the lease
// is not visible the operator does not know an auto-hold is imminent (U-4). The
// numbers come from the foundation lease logic; this component only formats them.

import { leaseRemainingMs, heartbeatMarginMs, leaseHeld } from "./gating";
import type { ManualSource } from "./manualSource";

export interface LeaseHeartbeatBarProps {
  source: ManualSource;
}

export function LeaseHeartbeatBar({ source }: LeaseHeartbeatBarProps) {
  const remaining = leaseRemainingMs(source);
  const margin = heartbeatMarginMs(source);
  const held = leaseHeld(source);
  return (
    <div
      className="oa-man-lease"
      role="status"
      aria-label="제어권 리스·하트비트"
      data-lease-held={held ? "true" : "false"}
    >
      <span className="oa-man-lease__item" data-field="lease-remaining">
        리스 잔여: {remaining} ms
      </span>
      <span className="oa-man-lease__item" data-field="heartbeat-margin">
        하트비트 여유: {margin} ms (타임아웃 {source.deadman.heartbeatTimeoutMs} ms)
      </span>
      <span className="oa-man-lease__item" data-field="lease-status">
        상태: {held ? "보유" : "미보유/만료"}
      </span>
    </div>
  );
}
