// Standing operator text for the S-12 threshold readout. Every string here states
// a BACKEND fact the screen only renders: the comparison lives in
// backend/gmo/isolation.py (|residual| >= threshold), and the residual itself is
// what backend/gmo/observer.py leaves after the model's own torque expectation is
// subtracted. Exported so the tests assert the shipped string rather than a copy,
// the same way detectionGate.ts exports its banners.

// NORM-009: the threshold is compared against the observer residual, never against
// the total torque the motor produces. Read as total torque, "4.0 Nm" means the arm
// stops whenever it produces 4 Nm — nonsense, because holding an outstretched arm
// against gravity already costs tens of Nm at the shoulder. The subtraction is
// spelled out because that is the sentence which makes the near-zero claim
// believable to an operator who has just seen a large torque reading elsewhere.
//
// The near-zero claim holds only for an identified model. FR-SAF-030 forces
// detection DISABLED exactly because an unidentified v2 friction model leaves a
// standing bias in the residual, and DetectionPanel renders that banner on this
// same screen — an unqualified promise here would contradict it and would teach
// the operator to read a biased residual as contact.
export const RESIDUAL_COMPARISON_NOTICE =
  "이 임계값은 관측기 잔차와 비교됩니다 — 모터가 내는 총 토크가 아닙니다 (FR-SAF-020). " +
  "잔차 = 실제 관절 토크 − (중력 + 마찰 + 관성으로 설명되는 토크) 이므로, " +
  "모델이 정확하다면 아무것도 팔을 밀지 않는 한 어떤 자세에서도 0 근처에 머뭅니다. " +
  "팔을 뻗어 든 자세는 어깨에서 이미 수십 Nm를 쓰지만, 그때도 잔차는 0 근처입니다. " +
  "다만 v2.0 마찰 모델이 식별되기 전(PG-FRIC-001 미통과)에는 마찰 항이 틀려 잔차에 편향이 남습니다 — " +
  "0에서 벗어난 값이 곧 접촉은 아니며, 충돌 감지가 비활성으로 강제되는 이유가 이것입니다 (FR-SAF-030).";

// The per-joint readout label. An unqualified "threshold" printed beside the effort
// limit reads as one ratio — "4 of the 40 Nm the motor can make" — which is the exact
// misreading NORM-009 rules against, so the label names the quantity being bounded.
export const THRESHOLD_READOUT_LABEL = "잔차 임계";

// The effort limit stays on screen because it is the ceiling the 0.1 x effort
// default came from (FR-SAF-020), but it is not what the threshold is compared to.
export const EFFORT_LIMIT_READOUT_LABEL = "effort 리밋(비교 대상 아님)";
