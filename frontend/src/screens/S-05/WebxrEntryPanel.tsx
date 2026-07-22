// The WebXR entry-point panel (CG-G-S05g, FR-GUI-005). The WebXR pose receiver is a
// SEPARATE HTTPS component from the SPA — WebXR requires a secure context, so it is
// HTTPS only, and it binds a port distinct from the SPA-serving port. The screen
// reads the backend's entry config and renders the entry point + the separation
// check; it opens no socket and serves nothing itself.
//
// When PG-VR-001 fails the native APK path, this WebXR path is the operational
// fallback (WP-3B-08) and the panel says so; when the gate is pending it is the
// standby entry, verdict undecided.

import { DEFAULT_BACKEND_PORT } from "../../config/endpoints";

import { webxrIsSeparateFromSpa, type VrEntryResolution } from "./gates";
import type { WebxrEntry } from "./teleopSource";

interface WebxrEntryPanelProps {
  webxr: WebxrEntry;
  resolution: VrEntryResolution;
}

export function WebxrEntryPanel({ webxr, resolution }: WebxrEntryPanelProps) {
  const separate = webxrIsSeparateFromSpa(webxr);
  const entryUrl = `${webxr.scheme}://${webxr.host}:${webxr.port}`;
  const fallbackActive = resolution.fallbackActive;

  return (
    <section className="oa-tel__webxr" aria-label="WebXR 진입점">
      <h2 className="oa-tel__h2">WebXR 진입점</h2>

      <p
        className="oa-tel__webxr-entry"
        data-field="webxr-entry"
        data-active={fallbackActive ? "true" : "false"}
      >
        진입 URL: <code data-field="webxr-url">{entryUrl}</code> ({webxr.sessionMode})
        {fallbackActive ? " · 폴백 활성" : " · 대기"}
      </p>

      <p
        className="oa-tel__webxr-sep"
        role="status"
        data-field="webxr-separation"
        data-separate={separate ? "true" : "false"}
      >
        {separate
          ? `HTTPS · SPA 포트(${DEFAULT_BACKEND_PORT})와 분리된 포트 ${webxr.port} — VR 수신 전용`
          : `분리 위반 — WebXR 포트가 SPA 포트(${DEFAULT_BACKEND_PORT})와 충돌하거나 HTTPS 아님`}
      </p>

      <dl className="oa-tel__kv">
        <div>
          <dt>TLS 인증서</dt>
          <dd data-field="tls-cert">{webxr.tlsCertPath}</dd>
        </div>
        <div>
          <dt>TLS 키</dt>
          <dd data-field="tls-key">{webxr.tlsKeyPath}</dd>
        </div>
      </dl>

      <div className="oa-tel__webxr-chain">
        <span>컨트롤러 프로필 폴백 체인 (xr-standard로 수렴):</span>
        <ol>
          {webxr.fallbackProfileChain.map((profile) => (
            <li key={profile}>
              <code>{profile}</code>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
