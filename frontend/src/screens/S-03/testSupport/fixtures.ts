// Test-only fixtures shaped by the frozen MOT contracts (03) and the CTR-ERR
// registry, the TypeScript analog of the 3A synthetic fixtures. Imported only from
// *.test.ts(x) under this screen, so it never enters the built bundle. The values
// mirror the spec's own tables (03 §2.1/§2.4/§2.8/§2.9/§2.10, error_registry.yaml)
// so the facade is exercised against realistic backend-shaped data without any
// real hardware.

import type {
  ErrorRegistryEntry,
  GainLimitProfile,
  GripperState,
  JointLimitRad,
  MotorDescriptor,
  MotorRuntimeState,
  MotorSetupSource,
} from "../motorDomain";

// The eight v2.0 motors (03 §2.1 CAN-ID map + §2.4 scale limits, right arm).
export const MOTORS: MotorDescriptor[] = [
  { jointName: "J1", motorType: "DM8009", sendCanId: 0x01, recvCanId: 0x11, pMaxRad: 12.5, vMaxRadS: 45, tMaxNm: 54 },
  { jointName: "J2", motorType: "DM8009", sendCanId: 0x02, recvCanId: 0x12, pMaxRad: 12.5, vMaxRadS: 45, tMaxNm: 54 },
  { jointName: "J3", motorType: "DM4340", sendCanId: 0x03, recvCanId: 0x13, pMaxRad: 12.5, vMaxRadS: 8, tMaxNm: 28 },
  { jointName: "J4", motorType: "DM4340", sendCanId: 0x04, recvCanId: 0x14, pMaxRad: 12.5, vMaxRadS: 8, tMaxNm: 28 },
  { jointName: "J5", motorType: "DM4310", sendCanId: 0x05, recvCanId: 0x15, pMaxRad: 12.5, vMaxRadS: 30, tMaxNm: 10 },
  { jointName: "J6", motorType: "DM4310", sendCanId: 0x06, recvCanId: 0x16, pMaxRad: 12.5, vMaxRadS: 30, tMaxNm: 10 },
  { jointName: "J7", motorType: "DM4310", sendCanId: 0x07, recvCanId: 0x17, pMaxRad: 12.5, vMaxRadS: 30, tMaxNm: 10 },
  { jointName: "J8", motorType: "DM4310", sendCanId: 0x08, recvCanId: 0x18, pMaxRad: 12.5, vMaxRadS: 30, tMaxNm: 10 },
];

// Mechanical hard-stop limits in rad (03 §2.9 URDF v2, right arm), 8 joints.
export const MECHANICAL_LIMITS_RAD: JointLimitRad[] = [
  { lo: -1.3963, hi: 3.4907 },
  { lo: -0.17453, hi: 3.3161 },
  { lo: -1.5708, hi: 1.5708 },
  { lo: 0, hi: 2.4435 },
  { lo: -1.5708, hi: 1.5708 },
  { lo: -0.7854, hi: 0.7854 },
  { lo: -1.5708, hi: 1.5708 },
  { lo: -1.5708, hi: 0 },
];

// A valid operational profile: every band inside the mechanical set above.
function conservativeLimits(): JointLimitRad[] {
  return MECHANICAL_LIMITS_RAD.map((limit) => ({
    lo: limit.lo + 0.05,
    hi: limit.hi - 0.05,
  }));
}

// Two named profiles (03 §2.8): the LeRobot-active follower and the compliant set.
export const PROFILES: GainLimitProfile[] = [
  {
    name: "lerobot_follower",
    kp: [240, 240, 240, 240, 24, 31, 25, 25],
    kd: [5, 5, 3, 5, 0.3, 0.3, 0.3, 0.3],
    operationalLimitsRad: conservativeLimits(),
  },
  {
    name: "compliant",
    kp: [70, 70, 70, 60, 10, 10, 10, 10],
    kd: [2.75, 2.5, 2.0, 2.0, 0.7, 0.6, 0.5, 0.2],
    operationalLimitsRad: conservativeLimits(),
  },
];

export const MOTOR_STATES: MotorRuntimeState[] = [
  { jointName: "J1", tempMosC: 41, tempRotorC: 38, errNibble: "1" },
  { jointName: "J2", tempMosC: 44, tempRotorC: 40, errNibble: "1" },
  { jointName: "J5", tempMosC: 52, tempRotorC: 49, errNibble: "B" },
];

// Gripper (J8 = DM4310, vMax 30 rad/s) with the misleading configured speed 50 from
// openarm_cell.yaml (03 §2.10) so the reachable-speed clamp is exercised.
export const GRIPPER: GripperState = {
  torquePu: 0.222,
  configuredSpeedRadS: 50,
  motorVMaxRadS: 30,
  openRad: null,
  closeRad: -1.4,
};

// The seven motor fault rows, mirrored from contracts/errors/error_registry.yaml so
// the ERR view has its recovery hints without the browser authoring them.
export const ERROR_REGISTRY: Record<string, ErrorRegistryEntry> = {
  "OA-MOT-008": {
    message: "과전압 (overvoltage)",
    recoveryHint: "즉시 홀드 후 전원 점검(권고 ≤32V/≤52V). 감속 프로파일 완화.",
    severity: "ERROR",
  },
  "OA-MOT-009": {
    message: "저전압 (undervoltage)",
    recoveryHint: "전원 점검(≥15V). 저전압은 회생(regen) 신호일 수 있으므로 감속 완화.",
    severity: "ERROR",
  },
  "OA-MOT-00A": {
    message: "과전류 (overcurrent)",
    recoveryHint: "토크 클램프 후 홀드. 충돌·끼임 물리 확인, 게인/페이로드 재검토.",
    severity: "ERROR",
  },
  "OA-MOT-00B": {
    message: "MOS 과온",
    recoveryHint: "궤적 중단 후 중력보상 홀드, 냉각 대기. 토크를 0으로 만들지 않는다(낙하).",
    severity: "ERROR",
  },
  "OA-MOT-00C": {
    message: "모터 코일 과온",
    recoveryHint: "궤적 중단 후 중력보상 홀드, 히스테리시스만큼 냉각 대기. 부하·게인 재검토.",
    severity: "ERROR",
  },
  "OA-MOT-00D": {
    message: "통신 두절 (communication loss)",
    recoveryHint: "커넥터·데이지체인 확인 후 재스캔. 백엔드 CAN 해제 후 진단.",
    severity: "ERROR",
  },
  "OA-MOT-00E": {
    message: "과부하 (overload)",
    recoveryHint: "토크 클램프 후 홀드. 정격 4.1kg/피크 6.0kg 대비 페이로드 재검토.",
    severity: "ERROR",
  },
};

// A fully-populated, loaded source (a profile active → control allowed).
export function loadedSource(overrides: Partial<MotorSetupSource> = {}): MotorSetupSource {
  return {
    motors: MOTORS,
    mechanicalLimitsRad: MECHANICAL_LIMITS_RAD,
    profiles: PROFILES,
    activeProfileName: "lerobot_follower",
    motorStates: MOTOR_STATES,
    gripper: GRIPPER,
    errorRegistry: ERROR_REGISTRY,
    ...overrides,
  };
}
