// Per-interface CAN status badge (FR-GUI-061). Renders the derived CAN state and,
// when an intruder is on the bus, the intruding PIDs (CG-G-03e). The badge colour
// follows the state: INTRUDED/CONFLICT/FAULT are danger, OWNED is nominal,
// UNOWNED is muted. The badge only observes; it never acts on the bus.

import {
  deriveCanState,
  hasIntruder,
  isControlBlocked,
  type CanInterfaceStatus,
  type CanState,
} from "./canStatus";

const STATE_TONE: Record<CanState, "nominal" | "muted" | "danger"> = {
  OWNED: "nominal",
  UNOWNED: "muted",
  INTRUDED: "danger",
  CONFLICT: "danger",
  FAULT: "danger",
};

const STATE_LABEL: Record<CanState, string> = {
  OWNED: "점유",
  UNOWNED: "미점유",
  INTRUDED: "외부 침입",
  CONFLICT: "충돌",
  FAULT: "링크 장애",
};

export interface CanBadgeProps {
  status: CanInterfaceStatus;
}

export function CanBadge({ status }: CanBadgeProps) {
  const state = deriveCanState(status);
  const blocked = isControlBlocked(status);
  return (
    <span
      className={`oa-badge oa-badge--${STATE_TONE[state]}`}
      data-can-state={state}
      data-control-blocked={blocked}
      role="status"
    >
      <span className="oa-badge__key">{status.iface}</span>
      <span className="oa-badge__value">{STATE_LABEL[state]}</span>
      {hasIntruder(status) && (
        <span className="oa-badge__intruders" data-testid="can-intruder-pids">
          침입 PID: {status.intruderPids.join(", ") || "미상"}
        </span>
      )}
    </span>
  );
}
