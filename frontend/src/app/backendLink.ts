// The shell's only outbound path to the backend, and what the operator is told when
// there is none. Both senders are null: no WebSocket client is constructed anywhere in
// this build yet. This module reports that as a visible failure instead of dropping the
// request, because a control the operator believes acted is worse than no control at
// all — NORM-007's ruling on a stop that reaches nothing.

export type CommandSender = () => void;

// The result of asking the backend to do something. `sent: true` means the request was
// handed to a transport, NOT that the robot acted on it: no acknowledgement is modelled
// here, so nothing in this type may be read as "the arm stopped".
export type CommandOutcome = { sent: true } | { sent: false; reason: string };

export const NO_LINK_REASON = "백엔드 링크가 없어 전달되지 않았습니다";
export const SEND_FAILED_REASON = "전송이 실패했습니다";

// STOP_HOLD sender (CTR-WS@v2 `stop_hold`, control_frame: false — any client may send
// it). Null until the WebSocket client is wired; replacing this null with that send is
// the whole wiring change.
export const STOP_HOLD_SENDER: CommandSender | null = null;

// Writer for the coupled use_velocity_and_torque flag. Null on the same terms as the
// stop sender: a toggle with no writer must report that it did not apply, not quietly
// redraw itself as though it had.
export const VELOCITY_TORQUE_WRITER: ((enabled: boolean) => void) | null = null;

// Hand a request to its sender, reporting absence and throw alike as an explicit
// failure. A sender that throws is the same outcome as no sender: nothing was delivered.
export function deliver(sender: CommandSender | null): CommandOutcome {
  if (!sender) {
    return { sent: false, reason: NO_LINK_REASON };
  }
  try {
    sender();
    return { sent: true };
  } catch (error) {
    return { sent: false, reason: `${SEND_FAILED_REASON} — ${String(error)}` };
  }
}
