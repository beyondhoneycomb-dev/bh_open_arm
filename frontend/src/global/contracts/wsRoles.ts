// Browser-side mirror of the CTR-WS@v1 role model, consumed by the E-Stop
// reachability matrix (CG-G-03b). The canon is the frozen envelope schema
// (contracts/ws/envelope.schema.json); wsRoles.test.ts asserts this mirror
// agrees with it. CTR-WS defines three transport roles and names the single
// control holder; WP-G-03 reduces that to the two-value axis the acceptance
// matrix ranges over — the control holder ("controller") versus everyone else
// ("observer") — because reachability only cares whether a client holds control.

// The transport roles CTR-WS@v1 defines, in schema order.
export const WS_ROLES: readonly string[] = ["observer", "operator", "admin"];

// The single role that may send control frames (CTR-WS@v1: control_holder_role).
export const WS_CONTROL_HOLDER_ROLE = "operator";

// An observer must never send a control frame (CTR-WS@v1). The E-Stop is a
// safety control, not a control-authority frame, so it stays reachable for
// observers regardless — that separation is exactly what CG-G-03b verifies.
export const OBSERVER_MAY_SEND_CONTROL_FRAME = false;

// The acceptance matrix ranges over "observer vs control-holder", collapsing the
// three transport roles onto whether this client currently holds control.
export const CONTROL_ROLES = ["observer", "controller"] as const;
export type ControlRole = (typeof CONTROL_ROLES)[number];
