// Route entry for S-03 (/motors), discovered by routes/screenResolver via its
// import.meta.glob. It wires the backend-owned source and the intent sink, then
// renders the MotorSetupScreen facade.
//
// The GUI never sees real hardware (02d §3): the MOT state (motor descriptors,
// temperatures, err nibbles, profiles, gripper endpoints) arrives on the single WS
// state frame, which a shared WS provider (WP-G-01/WP-G-00) supplies. Until that
// provider feeds a frame, the source is empty and the screen renders the safe,
// honest awaiting/blocked state — no profile loaded means control is blocked
// (CG-G-S03e), and absent data is shown as unavailable, never fabricated. The
// verified behaviour of the facade is proven against the 3A-style fixtures in the
// colocated tests; this wiring is the single seam where live frames enter.

import { MotorSetupScreen } from "./MotorSetupScreen";
import type { MotorSetupSink, MotorSetupSource } from "./motorDomain";

const AWAITING_SOURCE: MotorSetupSource = {
  motors: [],
  mechanicalLimitsRad: [],
  profiles: [],
  activeProfileName: null,
  motorStates: [],
  gripper: null,
  errorRegistry: {},
};

// Intent handlers reach the robot only through the backend gateway over the single
// WS command frame. Until the shared WS provider is mounted there is no transport
// bound, so these record nothing and change nothing — the awaiting source keeps the
// interactive controls disabled, so no intent is reachable in this state anyway.
const INERT_SINK: MotorSetupSink = {
  loadProfile: () => {},
  saveProfile: () => {},
  captureGripperEndpoint: () => {},
};

export default function MotorSetupRoute() {
  return <MotorSetupScreen source={AWAITING_SOURCE} sink={INERT_SINK} />;
}
