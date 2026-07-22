// S-02 (robot connection) local UI constants and the standing operator warnings.
// Every threshold or clamp described here is a BACKEND fact this screen only
// renders (02 §2.0.1/§2.0.3, FR-GUI-112/084): the screen is a facade, so it
// states these facts to the operator but never re-derives or enforces them.
// The two routes this screen owns are named here so the router branch and the
// tests share one source.

export const CONNECTION_ROUTE = "/connection";
export const HOME_ZERO_ROUTE = "/home-zero";

// The angle unit every joint number on this screen is shown in. The browser does
// NOT convert deg<->rad — CTR-UNIT@v1 (backend) owns that boundary — so telemetry
// and rest poses are rendered in their native radian unit with this label.
export const JOINT_ANGLE_UNIT = "rad";

// The silent lock that makes `side` mandatory (02 §2.0.3 F-6', config_openarm_
// follower.py:107-120). With `side` unset the backend clamps every joint limit to
// this band and send_action() clips silently — no error is raised. Rendered as
// text so the operator understands why the arm will not move; never applied here.
export const SIDE_UNSET_LOCK_BAND_DEG = 5;
export const SIDE_UNSET_LOCK_WARNING =
  `side 미선택 시 백엔드가 전 축 관절 리밋을 ±${SIDE_UNSET_LOCK_BAND_DEG}°로 잠그고 ` +
  `send_action()이 조용히 클리핑합니다 — 에러가 나지 않아 "리밋이 잘 걸렸다"로 ` +
  `오독되기 쉽습니다. 진행하려면 side를 먼저 선택하세요.`;

// The bringup is torque-OFF until the operator explicitly enables it (02 §2.0.4,
// FR-CON-062). Shown beside the read-only bringup so the de-energised state is
// never mistaken for a fault.
export const BRINGUP_READONLY_NOTICE =
  "connect_readonly()는 버스를 torque-OFF로 엽니다 — 손으로 팔을 움직여 방향·영점을 " +
  "검증하고, operator가 명시적으로 토크를 인가하기 전까지 무전원입니다.";

// The explicit set_zero flow re-establishes the joint zero every power session,
// because 0xFE power-cycle persistence is unconfirmed (02 §2.0.4 Q-6). Rendered so
// the operator knows the zero is not assumed to survive a power cycle.
export const SET_ZERO_SESSION_NOTICE =
  "0xFE 영점의 전원 사이클 영속성은 미확인입니다 — 매 전원 세션 시작에 명시적 set_zero로 " +
  "영점을 재확립합니다.";

// The unavoidable hardware-relink danger (02 §2.0.1 F-3', FR-GUI-084): the backend
// re-open runs the auto-zero path, so the current physical pose becomes the new
// zero with NO error, invalidating joint limits, virtual walls and the dataset
// frame at once. This is why the re-zero flow is gated by four steps.
export const REZERO_NEW_ZERO_WARNING =
  "재연결은 현재 물리 자세를 새 영점으로 확정합니다 — 조인트 리밋·가상벽·데이터셋 좌표계가 " +
  "무경고로 동시에 무효화됩니다. 현재 자세가 rest 자세인지 반드시 먼저 확인하세요.";

// CAN-FD is an `ip link` fact python-can cannot set (02 F-7', FR-GUI-112): the
// GUI verifies it, it does not configure it. The required bitrates are rendered
// from the frozen foundation constants so this screen states no second value.
export const CAN_FD_VERIFY_NOTICE =
  "CAN-FD는 python-can이 설정하지 못하는 ip link 사실입니다 — GUI는 이를 검증만 하며, " +
  "미검증 상태에서는 기동을 차단합니다.";
