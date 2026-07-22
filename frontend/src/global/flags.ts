// The two LeRobot config flags the GUI must surface and guard on every screen:
// use_velocity_and_torque (F-4') and push_to_hub (F-5'). Both default to a value
// that fails silently, so the GUI shows them at all times and forces a decision.
//
// use_velocity_and_torque is exposed ONLY as a single coupled switch (CG-G-03c):
// follower and leader move together. There is deliberately no per-arm setter in
// this module, because a mismatch kills `build_dataset_frame` with a KeyError at
// record time, and both-off silently drops the platform's force/compliance
// identity. The type carries one boolean, not one per arm, so a per-arm UI cannot
// be built on top of it.

export interface VelocityTorqueState {
  // The single coupled value applied to follower and leader together.
  enabled: boolean;
}

// FR-GUI-072: when the flag is off, torque/velocity are silently dropped and the
// dataset is position-only. The GUI shows this warning in a warning colour.
export const VELOCITY_TORQUE_OFF_WARNING = "토크·속도 데이터가 기록되지 않습니다";

// Whether the velocity/torque badge should render in its warning state.
export function velocityTorqueIsWarning(state: VelocityTorqueState): boolean {
  return !state.enabled;
}

// Build the next coupled state. This is the only mutator: it sets one value that
// applies to both arms, so follower and leader can never diverge.
export function setVelocityTorqueCoupled(enabled: boolean): VelocityTorqueState {
  return { enabled };
}

// push_to_hub defaults to true (F-5'): the record finally-block uploads the
// dataset — camera video included — to the Hugging Face Hub unless explicitly
// turned off. The GUI shows the value in a danger colour and forces an explicit
// confirmation before a collection can start with it on (CG-G-03d).
export interface PushToHubState {
  enabled: boolean;
  private: boolean;
  tags: readonly string[];
}

export const PUSH_TO_HUB_UPLOAD_WARNING =
  "수집 데이터가 Hugging Face Hub로 업로드됩니다";

// CG-G-03d: starting a collection while push_to_hub is on requires an explicit
// confirmation. This returns whether that confirmation gate must fire.
export function pushToHubRequiresConfirm(state: PushToHubState): boolean {
  return state.enabled;
}
