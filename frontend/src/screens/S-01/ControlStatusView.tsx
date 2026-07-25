// The control + CAN cluster of FR-GUI-100: connection/mode, CAN lock + intruder
// presence (FR-GUI-061 / CG-5-02g), and the coupled data flags use_velocity_and_
// torque + push_to_hub (FR-GUI-072/073 / CG-5-02f, always shown). Every value is
// the backend's; the dashboard reflects, it toggles nothing and detects nothing.

import { RENDER_STATE_CLASS, RENDER_STATE_LABEL } from "./severity";
import type { CanInterfaceStatus, ConnectionMode, DataFlags } from "./types";
import { UNAVAILABLE } from "./types";

interface ControlStatusViewProps {
  connection: ConnectionMode;
  can: readonly CanInterfaceStatus[];
  flags: DataFlags;
}

export function ControlStatusView({ connection, can, flags }: ControlStatusViewProps) {
  return (
    <section className="oa-dash__panel" aria-labelledby="oa-dash-control-title">
      <h2 id="oa-dash-control-title" className="oa-dash__panel-title">
        연결 · 제어권 · CAN
      </h2>

      <div className="oa-dash__tile" data-testid="fr100-connection">
        <span className="oa-dash__tile-label">연결 / 모드</span>
        <span className="oa-dash__tile-value" data-connected={connection.connected}>
          {connection.connected ? "연결됨" : "연결 안 됨"} · {connection.mode}
        </span>
        <span className="oa-dash__tile-sub" data-testid="control-holder">
          제어권 보유: {connection.controlHolder ?? "없음"}
        </span>
        <span className="oa-dash__tile-sub" data-testid="active-profile">
          활성 프로파일: {connection.activeProfileId ?? "없음"}
        </span>
      </div>

      <ul className="oa-dash__can-list" data-testid="fr100-can-lock">
        {can.map((iface) => {
          const renderState = iface.state ?? UNAVAILABLE;
          return (
            <li
              key={iface.iface}
              className={`oa-dash__can ${RENDER_STATE_CLASS[renderState]}`}
              data-testid={`can-${iface.iface}`}
              data-render-state={renderState}
            >
              <span className="oa-dash__can-name">{iface.iface}</span>
              <span className="oa-dash__can-state">{RENDER_STATE_LABEL[renderState]}</span>
              <span className="oa-dash__can-lock" data-lock-held={iface.lockHeld}>
                {iface.lockHeld ? "락 보유" : "락 없음"} · 바인딩 소켓 {iface.boundSocketCount}
              </span>
              <span
                className="oa-dash__can-intruder"
                data-testid={`intruder-${iface.iface}`}
                data-intruder-present={iface.intruderPresent}
              >
                {iface.intruderPresent
                  ? `침입자 감지 PID: ${iface.intruderPids.join(", ")}`
                  : "침입자 없음"}
              </span>
            </li>
          );
        })}
      </ul>

      <div className="oa-dash__flags">
        <div
          className="oa-dash__tile"
          data-testid="fr100-velocity-torque"
          data-enabled={flags.useVelocityAndTorque}
        >
          <span className="oa-dash__tile-label">use_velocity_and_torque</span>
          <span className="oa-dash__tile-value">
            {flags.useVelocityAndTorque ? "ON (커플드)" : "OFF"}
          </span>
          {flags.useVelocityAndTorque ? null : (
            <span className="oa-dash__tile-warn" data-testid="velocity-torque-warn">
              힘/컴플라이언스 정체성 손실 위험
            </span>
          )}
        </div>

        <div className="oa-dash__tile" data-testid="fr100-push-to-hub" data-enabled={flags.pushToHub}>
          <span className="oa-dash__tile-label">push_to_hub</span>
          <span className="oa-dash__tile-value">{flags.pushToHub ? "ON" : "OFF"}</span>
          {flags.pushToHub ? (
            <span className="oa-dash__tile-warn" data-testid="push-to-hub-warn">
              수집 데이터 외부 업로드 위험
            </span>
          ) : null}
        </div>
      </div>
    </section>
  );
}
