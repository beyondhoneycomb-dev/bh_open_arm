// Browser-side mirror of the CTR-WS@v2 role model, consumed by the stop-surface
// reachability matrix (CG-G-03b). The canon is the frozen envelope schema
// (contracts/ws/envelope.schema.json); wsRoles.test.ts asserts this mirror
// agrees with it. CTR-WS defines three transport roles and names the single
// control holder; WP-G-03 reduces that to the two-value axis the acceptance
// matrix ranges over — the control holder ("controller") versus everyone else
// ("observer") — because reachability only cares whether a client holds control.

// The transport roles CTR-WS@v2 defines, in schema order.
export const WS_ROLES: readonly string[] = ["observer", "operator", "admin"];

// The single role that may send control frames (CTR-WS@v2: control_holder_role).
export const WS_CONTROL_HOLDER_ROLE = "operator";

// An observer must never send a control frame (CTR-WS@v2). The soft stop is
// reachable anyway, and the mechanism is a specific frame rather than a promise:
// CTR-WS@v2 carries `stop_hold` with `control_frame: false`, so authorize_send
// admits it from every role. That is what makes CG-G-03b checkable — before the
// frame existed, an observer had nothing to send and this constant said only which
// frames were denied, not that any stop was permitted.
export const OBSERVER_MAY_SEND_CONTROL_FRAME = false;

// The frame an observer sends to stop the arm (`13` FR-GUI-065). Named here so the
// reachability matrix targets the frame the transport actually admits instead of a
// screen element that may or may not reach one.
export const STOP_HOLD_FRAME = "stop_hold";

// The acceptance matrix ranges over "observer vs control-holder", collapsing the
// three transport roles onto whether this client currently holds control.
export const CONTROL_ROLES = ["observer", "controller"] as const;
export type ControlRole = (typeof CONTROL_ROLES)[number];
