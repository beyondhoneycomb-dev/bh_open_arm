// The CAN-ID map + motor type + scale-limit (PMAX/VMAX/TMAX) table. Every value is
// a MotorDescriptor the backend RID read (WP-0B-07) produced; this component only
// renders them. T_MAX is the motor's torque limit and is legitimately shown in Nm
// (motor torque, not grasp force) — the N/Nm grasp-force ban (CG-G-S03a) is about
// the gripper panel, which is a separate component.

import type { MotorDescriptor } from "./motorDomain";

interface CanIdMotorTableProps {
  motors: readonly MotorDescriptor[];
}

function hex(id: number): string {
  return `0x${id.toString(16).toUpperCase().padStart(2, "0")}`;
}

export function CanIdMotorTable({ motors }: CanIdMotorTableProps) {
  return (
    <section className="oa-motors__panel" aria-labelledby="oa-motors-canmap-title">
      <h2 id="oa-motors-canmap-title" className="oa-motors__panel-title">
        CAN-ID 맵 · 모터 타입
      </h2>
      {motors.length === 0 ? (
        <p className="oa-motors__hint" role="status">
          모터 인벤토리 미가용 — 백엔드 RID 리드 대기 (awaiting backend RID read)
        </p>
      ) : (
        <div className="oa-motors__scroll">
          <table className="oa-motors__table">
            <thead>
              <tr>
                <th>관절</th>
                <th>모터</th>
                <th>Send ID</th>
                <th>Recv ID</th>
                <th>P_MAX (rad)</th>
                <th>V_MAX (rad/s)</th>
                <th>T_MAX (Nm)</th>
              </tr>
            </thead>
            <tbody>
              {motors.map((motor) => (
                <tr key={motor.jointName} data-motor={motor.jointName}>
                  <td>{motor.jointName}</td>
                  <td data-motor-type={motor.motorType}>{motor.motorType}</td>
                  <td>{hex(motor.sendCanId)}</td>
                  <td>{hex(motor.recvCanId)}</td>
                  <td>{motor.pMaxRad}</td>
                  <td>{motor.vMaxRadS}</td>
                  <td>{motor.tMaxNm}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
