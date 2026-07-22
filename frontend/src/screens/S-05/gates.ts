// The facade gates the teleop screen asks before it renders an affordance as
// enabled (WP-G-S05). Each reuses a backend verdict carried on the source rather
// than deciding anything itself: alignment convergence, session activity, the gate
// verdict. Nothing here clamps a value, decides a clutch threshold, or measures a
// latency — those are the backend's (`05` TEL, safety gate).

import { DEFAULT_BACKEND_PORT } from "../../config/endpoints";

import type { TeleopSource, VrGate, VrGateStatus, WebxrEntry } from "./teleopSource";

// CG-G-S05b: following cannot begin until alignment completes. `converged` is the
// backend `AlignRamp.is_converged` verdict; the screen renders no follow-start path
// that bypasses it, and this gate is what disables the follow-readiness affordance
// while alignment is incomplete.
export function canStartFollowing(source: TeleopSource): boolean {
  return source.alignment.converged;
}

// CG-G-S05f: while a VR session is active the GUI manual-control is disabled, so no
// two-source-simultaneous command state can exist. Session activity is a backend
// fact; this gate turns it into the manual-control disable.
export function manualControlDisabled(source: TeleopSource): boolean {
  return source.session.active;
}

export type CommandSource = "vr_apk" | "vr_webxr" | "gui_manual_available";

// The single active command source. When a VR session is active the operator's
// commands come from the headset (APK-UDP or the WebXR fallback), and GUI manual
// control is disabled; otherwise manual control is available. There is no state in
// which both are live — that is the exclusivity CG-G-S05f guards.
export function activeCommandSource(source: TeleopSource): CommandSource {
  if (!source.session.active) {
    return "gui_manual_available";
  }
  return source.session.transport === "webxr" ? "vr_webxr" : "vr_apk";
}

// CG-G-S05g: the WebXR entry point is HTTPS and on a port distinct from the SPA.
// The SPA-serving port is the backend default (13 §2.7); the browser compares the
// backend's declared WebXR port against it. This is a separation check on config,
// not domain logic.
export function webxrIsSeparateFromSpa(entry: WebxrEntry, spaPort: number = DEFAULT_BACKEND_PORT): boolean {
  return entry.scheme === "https" && entry.port !== spaPort;
}

export type VrOperationalPath = "apk_udp" | "webxr_fallback" | "pending";

export interface VrEntryResolution {
  operationalPath: VrOperationalPath;
  fallbackActive: boolean;
  gateStatus: VrGateStatus;
  message: string;
}

// PG-VR-001 → operational-path resolution. A `failed` gate (native APK unusable)
// drives the real WebXR fallback (WP-3B-08); a `pending` gate (the HW gate has not
// landed) is rendered as pending and fakes no verdict; a `passed` gate keeps the
// native APK path. The screen renders exactly this — it never promotes pending to
// pass or invents a fallback that the gate did not call for.
export function resolveVrEntry(gate: VrGate): VrEntryResolution {
  if (gate.status === "failed") {
    return {
      operationalPath: "webxr_fallback",
      fallbackActive: true,
      gateStatus: "failed",
      message: "PG-VR-001 실패(APK 불가) → WebXR / HTTPS:8443 폴백 (WP-3B-08)",
    };
  }
  if (gate.status === "pending") {
    return {
      operationalPath: "pending",
      fallbackActive: false,
      gateStatus: "pending",
      message: "PG-VR-001 미착지 (HW 게이트 WP-3C-04) — 검증 대기, 판정 없음",
    };
  }
  return {
    operationalPath: "apk_udp",
    fallbackActive: false,
    gateStatus: "passed",
    message: "PG-VR-001 통과 — 네이티브 APK (UDP) 경로",
  };
}
