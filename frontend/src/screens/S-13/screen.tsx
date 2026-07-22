// S-13 system/log screen (route /system, 13 §2.6). A facade over the backend's
// operations state: it renders the port-map comparison, RT/permission posture,
// diagnostic-bundle generator, and OA-* error lookup, and it owns none of their
// canon. The single WS is not used here — S-13's data is host reads served over
// same-origin REST — so there is no connect/disconnect/reconnect path and no way
// for this screen to disturb zeroing.

import { useEffect, useState } from "react";

import "./system.css";
import { DiagnosticBundleView } from "./DiagnosticBundleView";
import { ErrorLookupView } from "./ErrorLookupView";
import { PortCompareView } from "./PortCompareView";
import { RtCheckView } from "./RtCheckView";
import { createDefaultSource } from "./dataSource";
import type { SystemData, SystemDataSource } from "./types";

interface SystemScreenProps {
  source?: SystemDataSource;
}

type LoadState =
  | { phase: "loading" }
  | { phase: "error"; message: string }
  | { phase: "ready"; data: SystemData };

export default function SystemScreen({ source }: SystemScreenProps) {
  const [state, setState] = useState<LoadState>({ phase: "loading" });

  useEffect(() => {
    let active = true;
    const dataSource = source ?? createDefaultSource();
    dataSource
      .load()
      .then((data) => {
        if (active) {
          setState({ phase: "ready", data });
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setState({ phase: "error", message: error instanceof Error ? error.message : "unknown" });
        }
      });
    return () => {
      active = false;
    };
  }, [source]);

  return (
    <main className="oa-sys" aria-labelledby="oa-sys-title" data-testid="system-screen">
      <header className="oa-sys__head">
        <p className="oa-sys__id">S-13</p>
        <h1 id="oa-sys-title" className="oa-sys__title">
          시스템 / 로그
        </h1>
      </header>

      {state.phase === "loading" && (
        <p className="oa-sys__status" role="status" data-testid="system-loading">
          시스템 상태 로드 중…
        </p>
      )}
      {state.phase === "error" && (
        <p className="oa-sys__status oa-sys-alert" role="alert" data-testid="system-error">
          시스템 상태를 불러오지 못했습니다: {state.message}
        </p>
      )}
      {state.phase === "ready" && (
        <div className="oa-sys__grid">
          <PortCompareView canon={state.data.ports.canon} actual={state.data.ports.actual} />
          <RtCheckView rt={state.data.rt} registry={state.data.errorRegistry} />
          <DiagnosticBundleView manifest={state.data.bundle} />
          <ErrorLookupView registry={state.data.errorRegistry} />
        </div>
      )}
    </main>
  );
}
