// Dashboard (WP-G-S01, route /) — the last GUI screen (13/13). It AGGREGATES and
// RENDERS the values every domain already owns and COMPUTES NOTHING: no self-
// calculated metric, no self-decided threshold (CG-G-S01a / CG-5-02). A second
// aggregator that recomputed would be a second truth. Every value below is
// mirrored from a backend state contract as a TS render shape (types.ts) and read
// via a `source` prop with an offline default fixture — the same facade shape the
// committed siblings use. It opens no socket and offers no reconnect (invariant
// I-2); the single WebSocket is the foundation's (WP-G-01).
//
// The dashboard packs nine subsystems and a dozen FR-GUI-100 metrics onto one
// screen, so the CRITICAL-only area leads and the nine §4.3 subsystems are
// severity-sorted below it (02c §4.2 mitigation). The gates each panel keeps:
//   - CG-5-02a nine §4.3 subsystems, four states           → SubsystemGridView
//   - CG-G-S01e not-landed renders UNAVAILABLE, never OK    → severity + every tile
//   - CG-G-S01b all FR-GUI-100 items present                → the panels below
//   - CG-G-S01c camera tiles runtime-derived, no constant   → CameraStatusView
//   - CG-G-S01d cycle p95 from PG-RT-001b, no self-measure   → CycleTimeView
//   - CG-5-02e WARN cause split OR explicit-unimplemented    → CycleTimeView
//   - CG-5-02f use_velocity_and_torque + push_to_hub shown   → ControlStatusView
//   - CG-5-02g intruder-detection status shown               → ControlStatusView
//   - CG-5-02c public health omits holder/profile            → health.ts
//
// One panel here is a control rather than a readout: which end effector each arm
// carries is rig setup, and it sits beside the CAN readout because the fitted
// tool is what decides whether the eighth CAN id is addressed at all. It still
// computes nothing — the choices are the backend registry's and the fitted tool
// is the stored config's.

import { useMemo } from "react";

import "./dashboard.css";
import { CameraStatusView } from "./CameraStatusView";
import { ControlStatusView } from "./ControlStatusView";
import { CriticalAlertsView } from "./CriticalAlertsView";
import { CycleTimeView } from "./CycleTimeView";
import { EndEffectorPanel } from "./EndEffectorPanel";
import { ResourceView } from "./ResourceView";
import { SessionsView } from "./SessionsView";
import { SubsystemGridView } from "./SubsystemGridView";
import { defaultDashboardSource } from "./dashboardSource";
import type { DashboardSource } from "./types";

export interface DashboardScreenProps {
  source?: DashboardSource;
}

const DEFAULT_SOURCE: DashboardSource = defaultDashboardSource();

export default function DashboardScreen({ source }: DashboardScreenProps) {
  const resolved = source ?? DEFAULT_SOURCE;
  const data = useMemo(() => resolved.load(), [resolved]);

  return (
    <div className="oa-dash" data-screen="S-01">
      <header className="oa-dash__head">
        <p className="oa-dash__id">/</p>
        <h1 className="oa-dash__title">대시보드</h1>
      </header>

      <CriticalAlertsView subsystems={data.subsystems} />

      <div className="oa-dash__cols">
        <SubsystemGridView subsystems={data.subsystems} />

        <div className="oa-dash__col">
          <ControlStatusView connection={data.connection} can={data.can} flags={data.flags} />
          <EndEffectorPanel />
          <CycleTimeView cycleTime={data.cycleTime} />
        </div>

        <div className="oa-dash__col">
          <CameraStatusView cameras={data.cameras} />
          <ResourceView disk={data.disk} gpu={data.gpu} />
          <SessionsView sessions={data.sessions} unacked={data.unacked} />
        </div>
      </div>
    </div>
  );
}
