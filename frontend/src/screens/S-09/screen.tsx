// WP-G-S09 — the simulation screen (route /sim), mounted by the screen resolver.
// It is a facade onto the SIM domain: MuJoCo digital twin, dry-run, and the sim-vs-
// real ghost overlay, composed from the frozen SIM contracts in simDomain. The
// screen renders backend state and emits user intent; it re-implements no domain
// logic. Every value it shows originates in its `source` prop, which defaults to an
// offline fixture (AI-offline — the GUI never sees real hardware).
//
// The five acceptance gates it carries: the MJCF-is-not-a-hardware-spec disclaimer
// (CG-G-S09a), the stiff-gain twin/dry-run precondition (CG-G-S09b), the reconnect-
// free sim<->real swap (CG-G-S09c), the per-item dry-run report with its real-send
// hard gate (CG-G-S09d), and the unmistakable ghost overlay (CG-G-S09e).

import { useState } from "react";

import "./sim.css";
import { AssetDisclaimer } from "./AssetDisclaimer";
import { DryRunReport } from "./DryRunReport";
import { GainParityGate } from "./GainParityGate";
import { GhostOverlay } from "./GhostOverlay";
import { RobotBackendToggle } from "./RobotBackendToggle";
import { defaultSimSource, type SimSource } from "./simSource";
import type { ControlTarget, SimBackend } from "./simDomain";

interface SimScreenProps {
  source?: SimSource;
}

export default function SimScreen({ source = defaultSimSource() }: SimScreenProps) {
  const [backend, setBackend] = useState<SimBackend>(source.backend);
  const [controlTarget, setControlTarget] = useState<ControlTarget>(source.controlTarget);

  // Intent sinks. The twin, dry-run and real-send run on the backend; offline these
  // are no-ops. The screen decides none of those outcomes — it only signals intent.
  function startTwin(): void {}
  function startDryRun(): void {}
  function sendToReal(): void {}

  return (
    <section className="oa-sim" aria-labelledby="oa-sim-title">
      <header className="oa-sim__head">
        <p className="oa-sim__route">/sim</p>
        <h1 id="oa-sim-title" className="oa-sim__title">
          시뮬레이션
        </h1>
      </header>

      <div className="oa-sim__grid">
        <RobotBackendToggle
          backend={backend}
          controlTarget={controlTarget}
          onSelectBackend={setBackend}
          onSwapTarget={setControlTarget}
        />
        <GainParityGate
          gainProfile={source.gainProfile}
          onStartTwin={startTwin}
          onStartDryRun={startDryRun}
        />
        <AssetDisclaimer />
        <DryRunReport
          report={source.dryRunReport}
          controlTarget={controlTarget}
          onSendToReal={sendToReal}
        />
      </div>

      <GhostOverlay viewport={source.viewport} />
    </section>
  );
}
