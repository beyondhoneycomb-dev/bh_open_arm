// The drop report (CG-G-S07c, CG-G-S07d). WS-transmit drops and capture/encode
// drops are rendered in two SEPARATE regions and never summed into one figure —
// merging them would hide whether a lost frame was the browser link (preview /
// telemetry) or the camera pipeline (capture / encode). Each side carries its own
// drop-rate flag against the display bands (dropRate.ts); the counts are the
// backend's (WP-3B-12), the ratio is display-only.

import { flagForCounts, type DropFlag } from "./dropRate";
import type { DropReport } from "./types";

export interface DropReportViewProps {
  report: DropReport;
}

const FLAG_LABELS: Record<DropFlag, string> = {
  ok: "정상",
  warn: "경고 (>2%)",
  overload: "과부하 (>5%)",
};

function FlagBadge({ flag }: { flag: DropFlag }) {
  return (
    <span
      className={`oa-collect__drop-flag oa-collect__drop-flag--${flag}`}
      data-flag={flag}
      role="status"
    >
      {FLAG_LABELS[flag]}
    </span>
  );
}

export function DropReportView({ report }: DropReportViewProps) {
  const wsDropTotal = report.wsTransmit.reduce((sum, entry) => sum + entry.dropCount, 0);
  const captureDropTotal =
    report.camera.reduce((sum, entry) => sum + entry.missingRows + entry.frameNumberGaps, 0) +
    report.can.flaggedFrames +
    report.can.suspectedStaleFrames;

  const wsFlag = flagForCounts(wsDropTotal, report.frameCount);
  const captureFlag = flagForCounts(captureDropTotal, report.frameCount);

  return (
    <section className="oa-collect__drops" aria-labelledby="oa-collect-drops-title">
      <h2 id="oa-collect-drops-title" className="oa-collect__section-title">
        드롭 리포트
      </h2>
      <p className="oa-collect__drops-frames">에피소드 프레임 {report.frameCount}</p>

      <div className="oa-collect__drop-grid">
        <article className="oa-collect__drop-card" data-testid="drop-ws-transmit">
          <header className="oa-collect__drop-head">
            <h3 className="oa-collect__drop-title">WS 송출 드롭</h3>
            <FlagBadge flag={wsFlag} />
          </header>
          <p className="oa-collect__drop-total">
            합계 <strong data-testid="drop-ws-total">{wsDropTotal}</strong>
          </p>
          {report.wsTransmit.length === 0 ? (
            <p className="oa-collect__drop-empty">채널 드롭 없음</p>
          ) : (
            <ul className="oa-collect__drop-list">
              {report.wsTransmit.map((entry) => (
                <li key={entry.channel} className="oa-collect__drop-row">
                  <span className="oa-collect__drop-ch">{entry.channel}</span>
                  <span className="oa-collect__drop-n">{entry.dropCount}</span>
                  <span className="oa-collect__drop-class" data-class={entry.classification}>
                    {entry.classification}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </article>

        <article className="oa-collect__drop-card" data-testid="drop-capture-encode">
          <header className="oa-collect__drop-head">
            <h3 className="oa-collect__drop-title">캡처·인코딩 드롭</h3>
            <FlagBadge flag={captureFlag} />
          </header>
          <p className="oa-collect__drop-total">
            합계 <strong data-testid="drop-capture-total">{captureDropTotal}</strong>
          </p>
          <ul className="oa-collect__drop-list">
            {report.camera.map((entry) => (
              <li key={entry.slot} className="oa-collect__drop-row">
                <span className="oa-collect__drop-ch">{entry.slot}</span>
                <span className="oa-collect__drop-n">
                  누락 {entry.missingRows} · 프레임번호 공백 {entry.frameNumberGaps}
                </span>
              </li>
            ))}
            <li className="oa-collect__drop-row">
              <span className="oa-collect__drop-ch">CAN</span>
              <span className="oa-collect__drop-n">
                플래그 {report.can.flaggedFrames} · 정지의심 {report.can.suspectedStaleFrames}
              </span>
            </li>
          </ul>
        </article>
      </div>
    </section>
  );
}
