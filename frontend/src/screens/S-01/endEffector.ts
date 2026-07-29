// Operator copy for the end-effector selector. Every sentence states a BACKEND
// fact this screen only renders: which CAN ids an arm addresses follows from the
// fitted tool (backend.endeffector.tools.ToolDefinition.motor_send_ids), and
// nothing here derives, enforces or re-decides it.
//
// The consequence is spelled out beside each choice because a tool name does not
// carry it. A tool with an actuated gripper makes the arm address the eighth
// motor; addressing one that is not on the bus is answered by nobody, the
// transmit error counter climbs, and the controller drops to ERROR-PASSIVE —
// which then degrades the seven joints that ARE present. That is why the choice
// is not a cosmetic label and why the unmeasured cases below refuse to guess.

import type { ArmSide } from "../../config/schema";

export const ARM_SIDE_LABELS: Record<ArmSide, string> = {
  left: "왼팔 (left)",
  right: "오른팔 (right)",
};

// The gripper motor's CAN id, as the backend names it
// (backend.endeffector.GRIPPER_SEND_ID). Written once so the two sentences below
// cannot drift into stating two different ids.
const GRIPPER_CAN_ID = "0x08";

const MASS_UNIT = "kg";

export const PANEL_TITLE = "엔드이펙터 (장착 도구)";

export const DEFAULT_TOOL_NOTICE =
  "아직 아무것도 고르지 않은 팔은 그리퍼 모터가 없는 도구로 시작합니다. " +
  "없는 모터를 부르는 쪽은 조용히 버스를 망가뜨리고, 부르지 않는 쪽은 " +
  "그리퍼 명령 한 번이 거부되고 끝나기 때문입니다.";

export const GRIPPER_POLLED_CONSEQUENCE =
  "이 도구를 고르면 이 팔의 여덟 번째 모터(CAN id " +
  GRIPPER_CAN_ID +
  ")를 주기적으로 부릅니다. 실물 그리퍼가 달려 있지 않으면 아무도 응답하지 않는 " +
  "프레임이 쌓이고, 컨트롤러가 ERROR-PASSIVE로 떨어지면서 멀쩡한 나머지 축까지 " +
  "함께 나빠집니다. 실제로 달려 있을 때만 고르세요.";

export const GRIPPER_ABSENT_CONSEQUENCE =
  "이 도구를 고르면 이 팔의 여덟 번째 모터(CAN id " +
  GRIPPER_CAN_ID +
  ")를 부르지 않습니다. 팔 관절만 사용하고, 그리퍼를 여닫는 명령이 오면 거부됩니다.";

// Mass is a fact to show, never a gate. It cannot be read with torque off, so an
// empty value is the normal state of a bench that has not powered up yet.
export const MASS_UNMEASURED_TEXT = "무게 미측정";

export const MASS_UNMEASURED_DETAIL =
  "토크가 꺼진 상태에서는 도구 무게를 잴 수 없습니다. 비어 있는 것이 정상이고, " +
  "무게를 몰라도 도구 선택과 나머지 작업은 그대로 됩니다.";

export const TOOL_CHANGE_MASS_NOTICE =
  "도구를 바꾸면 무게는 미측정으로 돌아갑니다. 이전 도구의 무게를 새 도구 것으로 " +
  "물려주면 틀린 값이 그대로 중력보상에 들어갑니다.";

export const TOOLS_LOADING_TEXT = "백엔드에서 도구 목록을 읽는 중입니다.";

export const TOOLS_UNREADABLE_TEXT =
  "백엔드에서 도구 목록을 읽지 못했습니다. 이 화면은 도구 목록을 따로 갖고 있지 않으므로 " +
  "선택지를 표시하지 않습니다.";

export const CONFIG_LOADING_TEXT = "설정을 읽는 중입니다.";

export const CONFIG_UNREADABLE_TEXT =
  "설정을 읽지 못했습니다. 어느 도구가 장착되어 있는지 표시할 수 없습니다.";

// The stored subobject did not parse, so what the control shows is the fallback
// (the tool with no gripper motor), not what the bench was last told.
export const CONFIG_DEFAULTED_TEXT =
  "저장된 엔드이펙터 설정을 읽지 못해 기본값(그리퍼 모터가 없는 도구)을 표시하고 있습니다. " +
  "실제로 장착된 도구를 다시 골라 저장하세요.";

export const SAVE_FAILED_TEXT =
  "선택을 저장하지 못했습니다. 아래에 표시된 선택은 백엔드에 저장되어 있는 값이며, " +
  "방금 누른 값이 아닙니다.";

export function massFactText(massKg: number | null): string {
  if (massKg === null) {
    return MASS_UNMEASURED_TEXT;
  }
  return `무게 ${massKg} ${MASS_UNIT}`;
}

// The stored id is not in the backend's registry. Which motors that tool puts on
// the bus is then unknown, so the control shows no selection at all rather than
// pointing at a neighbouring row.
export function unknownToolText(toolId: string): string {
  return (
    `저장된 도구 id(${toolId})가 백엔드 등록 목록에 없습니다. ` +
    "어떤 도구인지 확정할 수 없어 선택 상태를 표시하지 않습니다. " +
    "실제로 장착된 도구를 아래에서 고르세요."
  );
}
