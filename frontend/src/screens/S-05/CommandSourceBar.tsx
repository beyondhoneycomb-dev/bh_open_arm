// Command-source exclusivity (CG-G-S05f, FR-GUI-096). While a VR session is active
// the operator's commands come from the headset and GUI manual control is disabled;
// there is no UI state in which both sources can issue commands at once. This bar
// renders the single active source and the manual-control disable, and it hosts the
// screen's only manual-control affordance so that affordance is provably disabled
// during a session.

import { activeCommandSource, manualControlDisabled, type CommandSource } from "./gates";
import type { TeleopSource } from "./teleopSource";

const SOURCE_LABELS: Readonly<Record<CommandSource, string>> = {
  vr_apk: "VR 세션 (네이티브 APK · UDP)",
  vr_webxr: "VR 세션 (WebXR 폴백)",
  gui_manual_available: "GUI 수동 조작 가능",
};

interface CommandSourceBarProps {
  source: TeleopSource;
  onManualControl: () => void;
}

export function CommandSourceBar({ source, onManualControl }: CommandSourceBarProps) {
  const active = activeCommandSource(source);
  const manualDisabled = manualControlDisabled(source);

  return (
    <section className="oa-tel__source" aria-label="명령 소스 배타성">
      <h2 className="oa-tel__h2">명령 소스</h2>
      <p className="oa-tel__source-active" role="status" data-field="command-source" data-source={active}>
        활성 소스: {SOURCE_LABELS[active]}
      </p>
      <button
        type="button"
        className="oa-tel__manual-btn"
        data-field="manual-control"
        data-disabled={manualDisabled ? "true" : "false"}
        disabled={manualDisabled}
        onClick={onManualControl}
      >
        GUI 수동 조작
      </button>
      <p className="oa-tel__source-note">
        {manualDisabled
          ? "VR 세션 활성 — 수동 조작 비활성 (두 소스 동시 발행 불가)"
          : "VR 세션 비활성 — 수동 조작 허용"}
      </p>
    </section>
  );
}
