// Preview-vs-recording isolation panel (CG-G-S06c). WP-3C-03 guarantees preview
// is orthogonal to recording: the preview reads through a non-blocking
// `read_latest()` and cannot back-pressure capture, so a camera's preview may be
// OFF while it keeps recording, and the record drop rate does not change with the
// preview switch. This panel renders both numbers SEPARATELY — the backend record
// drop fraction and the preview pipe counters — so the two are never conflated,
// and shows each camera's preview switch state beside its record drop.

import type { CameraRuntime } from "./source";

interface PreviewIsolationPanelProps {
  cameras: Readonly<Record<string, CameraRuntime>>;
  masterPreviewEnabled: boolean;
  onToggleCameraPreview: (slot: string, enabled: boolean) => void;
  onToggleMasterPreview: (enabled: boolean) => void;
}

export function PreviewIsolationPanel({
  cameras,
  masterPreviewEnabled,
  onToggleCameraPreview,
  onToggleMasterPreview,
}: PreviewIsolationPanelProps) {
  const entries = Object.entries(cameras);
  return (
    <section className="oa-cam__panel" aria-labelledby="oa-cam-preview-title">
      <div className="oa-cam__panel-head">
        <h2 id="oa-cam-preview-title" className="oa-cam__panel-title">
          프리뷰 ⟂ 기록 (격리)
        </h2>
        <label className="oa-cam__master">
          <input
            type="checkbox"
            checked={masterPreviewEnabled}
            onChange={(event) => onToggleMasterPreview(event.target.checked)}
            data-action="toggle-master-preview"
          />
          프리뷰 마스터 스위치
        </label>
      </div>
      <p className="oa-cam__panel-note">
        프리뷰는 비블로킹 <code>read_latest()</code>만 사용한다 — ON/OFF는 기록 드롭률에 영향을 주지
        않으며, 녹화 중에도 프리뷰를 끌 수 있다.
      </p>
      <table className="oa-cam__stats">
        <thead>
          <tr>
            <th scope="col">카메라</th>
            <th scope="col">프리뷰</th>
            <th scope="col">기록 드롭률</th>
            <th scope="col">프리뷰 enc/tx/drop/skip</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([slot, runtime]) => (
            <tr key={slot} data-preview-row={slot}>
              <td className="oa-cam__stats-key">{slot}</td>
              <td>
                <label className="oa-cam__toggle">
                  <input
                    type="checkbox"
                    checked={runtime.previewEnabled}
                    onChange={(event) => onToggleCameraPreview(slot, event.target.checked)}
                    data-action="toggle-preview"
                    data-preview-slot={slot}
                  />
                  {runtime.previewEnabled ? "ON" : "OFF"}
                </label>
              </td>
              <td data-record-drop={slot}>{(runtime.recordDropFraction * 100).toFixed(1)}%</td>
              <td data-preview-counters={slot}>
                {runtime.preview.encoded}/{runtime.preview.transmitted}/{runtime.preview.dropped}/
                {runtime.preview.skipped}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
