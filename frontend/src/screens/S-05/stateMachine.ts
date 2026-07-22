// The teleop state-machine catalog (`05` §4.1, FR-TEL-077). This is the 11-state
// machine's DESCRIPTION — the id, name, per-tick motor output and hold flag of each
// state, plus the forbidden transitions (`05` §4.2) — as read-only data the screen
// renders. It is not an executable state machine: the machine lives in the backend
// `Teleoperator`, and `AlignmentStatus.currentState` carries which state the backend
// is in. The screen highlights that state and never drives a transition itself.
//
// The value of encoding the forbidden transitions here is display, not enforcement:
// the screen shows an operator WHY recovery from a hold must pass back through
// ALIGNING (S3) rather than resuming FOLLOWING (S4) directly, which is the whole
// reason re-engage exists as an explicit control.

export type TeleopStateId =
  | "S0"
  | "S1"
  | "S2"
  | "S3"
  | "S4"
  | "S5"
  | "S6"
  | "S7"
  | "S8"
  | "S9"
  | "S10";

export interface TeleopStateInfo {
  id: TeleopStateId;
  name: string;
  label: string;
  motorOutput: string;
  // True for states that hold position and refuse an implicit resume to FOLLOWING;
  // the only exit is an explicit operator re-engage back through ALIGNING.
  isHold: boolean;
}

// In `05` §4.1 table order, which is the boot/recovery flow, not numeric order.
export const TELEOP_STATES: readonly TeleopStateInfo[] = [
  {
    id: "S0",
    name: "IDLE",
    label: "대기",
    motorOutput: "홀드 유지 (send_action(q=qh)). disable_torque는 rest 자세에서만",
    isHold: false,
  },
  {
    id: "S10",
    name: "RECOVERY_CHECK",
    label: "복구 점검",
    motorOutput: "enable 금지 · 명령 송신 없음 (읽기만)",
    isHold: false,
  },
  {
    id: "S1",
    name: "HOMING",
    label: "홈 복귀",
    motorOutput: "저속 램프 (첫 q_des = 실측 q, 30% kp → 램프업)",
    isHold: false,
  },
  {
    id: "S2",
    name: "HOLD",
    label: "홀드",
    motorOutput: "send_action(q=qh) 지속 송신",
    isHold: true,
  },
  {
    id: "S3",
    name: "ALIGNING",
    label: "정렬",
    motorOutput: "align_target을 rate로 램프하여 send_action (급발진 방지)",
    isHold: false,
  },
  {
    id: "S4",
    name: "FOLLOWING",
    label: "추종",
    motorOutput: "send_action(q_ik) (리밋·워크스페이스·속도 클램프 통과)",
    isHold: false,
  },
  {
    id: "S5",
    name: "LINK_LOST",
    label: "링크 소실",
    motorOutput: "명령 송신 절대 중단 금지 · 감속 후 홀드",
    isHold: true,
  },
  {
    id: "S6",
    name: "PAUSED",
    label: "일시정지 / 클러치 해제",
    motorOutput: "홀드 · 기준점 파기 + One-Euro reset()",
    isHold: true,
  },
  {
    id: "S7",
    name: "IK_FAULT",
    label: "IK 결함",
    motorOutput: "홀드 · 마지막 유효 관절각 유지 + HUD 경고",
    isHold: true,
  },
  {
    id: "S8",
    name: "ESTOP",
    label: "비상정지",
    motorOutput: "operational hold(기본, 낙하 없음) 또는 Cat-0 물리 차단(낙하)",
    isHold: true,
  },
  {
    id: "S9",
    name: "STOPPING",
    label: "정지 중",
    motorOutput: "홈으로 저속 이동 → (선택) disable_torque → 낙하",
    isHold: false,
  },
];

export interface ForbiddenTransition {
  from: string;
  to: string;
  reason: string;
}

// `05` §4.2 forbidden transitions — the invariants the backend enforces and the
// screen explains. The recurring shape is "a hold can never resume FOLLOWING
// directly; it must re-align first".
export const FORBIDDEN_TRANSITIONS: readonly ForbiddenTransition[] = [
  { from: "S5", to: "S4", reason: "링크 복구 후 즉시 추종 금지 — 반드시 S3(재정렬) 경유" },
  { from: "S6", to: "S4", reason: "클러치 재체결 후 즉시 추종 금지 — S3 경유" },
  { from: "S7", to: "S4", reason: "IK 결함 복구 후 즉시 추종 금지 — S3 경유" },
  { from: "S8", to: "S2", reason: "E-Stop 해제는 S10 → S1부터 (직행 금지)" },
  {
    from: "*",
    to: "세션 재연결",
    reason: "어떤 전이도 로봇 세션을 재연결(재open)하지 않는다 — 재연결이 현재 자세를 영점으로 확정해 영점을 파괴한다 (I-2, §4.2 #5)",
  },
  { from: "*", to: "CAN 중단", reason: "어떤 상태에서든 CAN 명령 스트림 중단 금지 (S0/S9 의도적 disable 제외)" },
  { from: "S3", to: "S3(Δ≠0)", reason: "S3 진입 시 delta는 0에서 시작 (클러치 재파지 순간)" },
];

export function stateById(id: TeleopStateId): TeleopStateInfo {
  const found = TELEOP_STATES.find((state) => state.id === id);
  if (!found) {
    throw new Error(`unknown teleop state id: ${id}`);
  }
  return found;
}

export function isFollowingState(id: TeleopStateId): boolean {
  return id === "S4";
}

export function isHoldState(id: TeleopStateId): boolean {
  return stateById(id).isHold;
}
