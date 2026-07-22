// SocketCAN setup/diagnostics view (CG-G-S02e, FR-GUI-112). It renders the
// per-interface CAN state from the WP-G-03 foundation detectors and surfaces the
// CAN-FD startup blockers. The verdict (blocked / clear) is computed by the
// foundation's canStartupBlockers, folded across interfaces by canFd.ts — this
// view only displays it and the required 1 Mbps / 5 Mbps bitrates. It sets nothing.

import { CanBadge, deriveCanState, type CanInterfaceStatus } from "../../global";
import { CAN_FD_VERIFY_NOTICE } from "./constants";
import { canStartupBlockersAll, startupBlockedByCan } from "./canFd";
import { CAN_FD_NOMINAL_BITRATE, CAN_FD_DATA_BITRATE } from "./connectionSource";

interface CanDiagnosticsProps {
  interfaces: readonly CanInterfaceStatus[];
}

function mbps(bitsPerSecond: number): string {
  return `${bitsPerSecond / 1_000_000} Mbps`;
}

export function CanDiagnostics({ interfaces }: CanDiagnosticsProps) {
  const blocked = startupBlockedByCan(interfaces);
  const blockers = canStartupBlockersAll(interfaces);

  return (
    <section className="oa-s02-can" aria-labelledby="oa-s02-can-title" data-panel="can">
      <h2 id="oa-s02-can-title" className="oa-s02__panel-title">
        SocketCAN 진단
      </h2>

      <p className="oa-s02-can__requirement" role="note">
        {`필수 CAN-FD 비트레이트 — 공칭 ${mbps(CAN_FD_NOMINAL_BITRATE)} / 데이터 ${mbps(CAN_FD_DATA_BITRATE)}. `}
        {CAN_FD_VERIFY_NOTICE}
      </p>

      <ul className="oa-s02-can__list">
        {interfaces.map((iface) => (
          <li key={iface.iface} className="oa-s02-can__row" data-iface={iface.iface}>
            <CanBadge status={iface} />
            <span className="oa-s02-can__state" data-can-state={deriveCanState(iface)}>
              {deriveCanState(iface)}
            </span>
            <span
              className={`oa-s02-can__fd oa-s02-can__fd--${iface.canFdConfigured ? "ok" : "bad"}`}
              data-can-fd={iface.canFdConfigured ? "verified" : "unverified"}
            >
              {iface.canFdConfigured ? "CAN-FD 검증됨" : "CAN-FD 미검증"}
            </span>
          </li>
        ))}
      </ul>

      <p
        className={`oa-s02-can__startup oa-s02-can__startup--${blocked ? "blocked" : "clear"}`}
        role="status"
        data-startup={blocked ? "blocked" : "clear"}
      >
        {blocked ? "기동 차단: CAN-FD 미검증" : "CAN-FD 검증 완료 — 기동 가능"}
      </p>

      {blocked && (
        <ul className="oa-s02-can__blockers" role="alert">
          {blockers.length > 0 ? (
            blockers.map((reason) => <li key={reason}>{reason}</li>)
          ) : (
            <li>CAN 인터페이스가 없습니다 — 검증할 대상이 없어 기동 불가</li>
          )}
        </ul>
      )}
    </section>
  );
}
