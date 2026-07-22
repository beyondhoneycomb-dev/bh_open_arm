// The VR-session view (FR-GUI-005, WP-3B-07/08, WP-3C-04). It renders the live VR
// session (mode, transport, reference/pose space, logged controller profiles) and
// the PG-VR-001 gate state that decides which pose path is operational. PG-VR-001 is
// a HARDWARE gate that has not landed, so its verdict arrives as WS state that is
// currently "pending" — this view renders that pending state as a badge and never
// fabricates a verdict. A real `failed` (native APK unusable) shows the WebXR
// fallback as operational; the fallback path is real (WP-3B-08), not faked.

import { resolveVrEntry, type VrOperationalPath } from "./gates";
import type { VrGateStatus, VrSessionStatus } from "./teleopSource";
import type { VrGate } from "./teleopSource";

const GATE_LABELS: Readonly<Record<VrGateStatus, string>> = {
  pending: "대기 (미착지)",
  passed: "통과",
  failed: "실패",
};

const PATH_LABELS: Readonly<Record<VrOperationalPath, string>> = {
  apk_udp: "네이티브 APK (UDP)",
  webxr_fallback: "WebXR 폴백 (HTTPS:8443)",
  pending: "미결정 (게이트 대기)",
};

interface VrSessionViewProps {
  session: VrSessionStatus;
  gate: VrGate;
}

export function VrSessionView({ session, gate }: VrSessionViewProps) {
  const resolution = resolveVrEntry(gate);

  return (
    <section className="oa-tel__session" aria-label="VR 세션">
      <h2 className="oa-tel__h2">VR 세션</h2>

      <p
        className="oa-tel__vr-gate"
        role="status"
        data-field="vr-gate"
        data-status={gate.status}
      >
        {gate.id}: {GATE_LABELS[gate.status]} — {gate.note}
      </p>

      <p
        className="oa-tel__vr-path"
        role="status"
        data-field="operational-path"
        data-path={resolution.operationalPath}
        data-fallback={resolution.fallbackActive ? "true" : "false"}
      >
        운영 경로: {PATH_LABELS[resolution.operationalPath]} — {resolution.message}
      </p>

      <dl className="oa-tel__kv">
        <div>
          <dt>세션 활성</dt>
          <dd data-field="session-active">{session.active ? "활성" : "비활성"}</dd>
        </div>
        <div>
          <dt>모드</dt>
          <dd>{session.mode}</dd>
        </div>
        <div>
          <dt>헤드셋</dt>
          <dd>{session.headsetConnected ? "연결됨" : "미연결"}</dd>
        </div>
        <div>
          <dt>전송</dt>
          <dd>{session.transport === "webxr" ? "WebXR" : `APK UDP :${session.udpPort}`}</dd>
        </div>
        <div>
          <dt>reference space</dt>
          <dd>{session.referenceSpace}</dd>
        </div>
        <div>
          <dt>pose space</dt>
          <dd>{session.poseSpace}</dd>
        </div>
      </dl>

      <div className="oa-tel__profiles">
        <span>컨트롤러 프로필 (inputSources 로그):</span>
        {session.controllerProfiles.length === 0 ? (
          <span data-field="profiles-empty"> 없음 (세션 미시작)</span>
        ) : (
          <ol>
            {session.controllerProfiles.map((profile) => (
              <li key={profile}>
                <code>{profile}</code>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}
