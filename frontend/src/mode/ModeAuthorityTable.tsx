// The eight-mode authority table (FR-GUI-080). One row per mode, naming who holds
// send_action, whether the mode drives the real CAN bus, and — for MOTOR_SETUP
// only — that an external CAN client is permitted because the bus is not held
// (FR-GUI-086, CG-G-04e). The active mode is marked. The table renders the frozen
// catalog from modes.ts; it decides no authority itself.

import { HOLDER_LABELS, MODES, type ModeId } from "./modes";

export interface ModeAuthorityTableProps {
  activeMode: ModeId;
}

export function ModeAuthorityTable({ activeMode }: ModeAuthorityTableProps) {
  return (
    <table className="oa-authority-table" aria-label="8모드 제어권 표">
      <thead>
        <tr>
          <th scope="col">모드</th>
          <th scope="col">send_action 권리</th>
          <th scope="col">실기 CAN 구동</th>
          <th scope="col">외부 CAN 클라이언트</th>
        </tr>
      </thead>
      <tbody>
        {MODES.map((mode) => (
          <tr
            key={mode.id}
            data-mode={mode.id}
            aria-current={mode.id === activeMode ? "true" : undefined}
          >
            <th scope="row">{mode.label}</th>
            <td>{HOLDER_LABELS[mode.holder]}</td>
            <td>{mode.drivesRealBus ? "예" : "아니오"}</td>
            <td>{mode.allowsExternalCanClient ? "허용 (CAN 미점유)" : "불가"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
