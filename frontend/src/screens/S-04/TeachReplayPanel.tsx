// Teach-list CRUD and replay (WP-G-S04, FR-MAN-039..041). Capture the current pose
// as a waypoint, then create/delete/duplicate/reorder the list; the list itself is
// the backend teach store's (the screen calls store intents, it holds no canon).
// Replay is disabled unless the backend pre-verify passes (CG-G-S04h) AND the
// point's zero method matches the robot's current zero record (FR-MAN-040) — a
// point captured under a different zero would drive to a different physical pose.

import { PreVerifyReport } from "./PreVerifyReport";
import type { ManualCommand } from "./commands";
import type { ArmSide, TeachStatus, TeachPoint } from "./manualSource";

export interface TeachReplayPanelProps {
  teach: TeachStatus;
  side: ArmSide;
  canMove: boolean;
  onCapture: () => void;
  onDelete: (id: string) => void;
  onDuplicate: (id: string) => void;
  onReorder: (id: string, direction: "up" | "down") => void;
  onCommand: (command: ManualCommand) => void;
}

export function TeachReplayPanel({
  teach,
  side,
  canMove,
  onCapture,
  onDelete,
  onDuplicate,
  onReorder,
  onCommand,
}: TeachReplayPanelProps) {
  function replayEnabled(point: TeachPoint): boolean {
    return canMove && teach.preVerify.passed && !point.zeroMismatch;
  }

  function replay(point: TeachPoint): void {
    if (replayEnabled(point)) {
      onCommand({ op: "replay_execute", pointId: point.id, side });
    }
  }

  return (
    <section className="oa-man-teach" aria-labelledby="oa-man-teach-title">
      <header className="oa-man-teach__head">
        <h2 id="oa-man-teach-title">티칭 · 재생</h2>
        <button
          type="button"
          className="oa-man-teach__capture"
          data-field="teach-capture"
          onClick={onCapture}
        >
          현재 자세 캡처
        </button>
      </header>

      <PreVerifyReport report={teach.preVerify} label="재생 궤적 사전 검증" />

      <ul className="oa-man-teach__list">
        {teach.points.map((point) => (
          <li key={point.id} className="oa-man-teach__item" data-teach-point={point.id}>
            <span className="oa-man-teach__name">{point.name}</span>
            <span className="oa-man-teach__meta">
              {point.armSide} · zero={point.zeroMethod} · gain={point.gainProfile}
            </span>
            {point.zeroMismatch && (
              <span className="oa-man-teach__mismatch" role="alert" data-field="zero-mismatch">
                영점 불일치 — 재생 차단
              </span>
            )}
            <span className="oa-man-teach__actions">
              <button type="button" onClick={() => onReorder(point.id, "up")} aria-label="위로">
                ↑
              </button>
              <button type="button" onClick={() => onReorder(point.id, "down")} aria-label="아래로">
                ↓
              </button>
              <button
                type="button"
                onClick={() => onDuplicate(point.id)}
                data-field="teach-duplicate"
              >
                복제
              </button>
              <button type="button" onClick={() => onDelete(point.id)} data-field="teach-delete">
                삭제
              </button>
              <button
                type="button"
                className="oa-man-teach__replay"
                data-field="teach-replay"
                data-point={point.id}
                disabled={!replayEnabled(point)}
                onClick={() => replay(point)}
              >
                재생
              </button>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
