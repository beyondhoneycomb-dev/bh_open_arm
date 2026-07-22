// The three control-authority roles, from CTR-WS@v1 roles.values (FR-OPS-078).
// observer reads only and may send no control frame (CTR-WS
// observer_may_send_control_frame = false); operator is the single control holder
// (CTR-WS control_holder_role = "operator"); admin additionally may force-release a
// lease and change the safety envelope. The backend arbitrates the single control
// authority — this type only names the roles the GUI renders.

export type LeaseRole = "observer" | "operator" | "admin";

export const ROLE_LABELS: Readonly<Record<LeaseRole, string>> = {
  observer: "관찰자",
  operator: "오퍼레이터",
  admin: "관리자",
};

// Whether a role may hold the control lease. Only the operator (and admin acting as
// one) sends control frames; an observer is read-only.
export function mayHoldControl(role: LeaseRole): boolean {
  return role !== "observer";
}
