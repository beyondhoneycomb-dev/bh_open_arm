// S-02 robot connection screen body. It composes the connection route
// (/connection: side force, hardware inventory, SocketCAN diagnostics, first-
// connect wizard, profile select, connect_readonly bringup) and the home-zero
// route (/home-zero: explicit-zero confirm, calibration render, 4-step re-zero).
// It holds only ephemeral UI state (chosen side, chosen profile) in React state —
// never in localStorage, which would be a second config canon. Every domain fact
// comes from the injected `source`; the screen renders it and sends intent.

import { useState } from "react";

import { CONNECTION_ROUTE, HOME_ZERO_ROUTE } from "./constants";
import { startupBlockedByCan } from "./canFd";
import { BringupPanel } from "./BringupPanel";
import { CalibrationView } from "./CalibrationView";
import { CanDiagnostics } from "./CanDiagnostics";
import { FirstConnectWizard } from "./FirstConnectWizard";
import { HardwareInventory } from "./HardwareInventory";
import { ProfileSelect } from "./ProfileSelect";
import { RezeroDialog } from "./RezeroDialog";
import { SideSelector } from "./SideSelector";
import { ZeroConfirmView } from "./ZeroConfirmView";
import { defaultConnectionSource, type ConnectionSource } from "./connectionSource";
import type { BringupBackendAction } from "./bringup";
import type { SideSelection } from "./sideSelection";
import type { RezeroAuditEntry } from "./rezeroFlow";

export type ConnectionRoute = typeof CONNECTION_ROUTE | typeof HOME_ZERO_ROUTE;

interface ConnectionScreenProps {
  route: ConnectionRoute;
  source?: ConnectionSource;
  // Emitted bringup intents and completed re-zero audits are surfaced for the
  // shell to wire to the WS command channel; both default to no-ops offline.
  onBringupAction?: (action: BringupBackendAction) => void;
  onRezeroAudit?: (entry: RezeroAuditEntry) => void;
}

export function ConnectionScreen({
  route,
  source = defaultConnectionSource(),
  onBringupAction,
  onRezeroAudit,
}: ConnectionScreenProps) {
  const [side, setSide] = useState<SideSelection>(null);
  const [selectedProfile, setSelectedProfile] = useState<string | null>(null);

  const canStartupBlocked = startupBlockedByCan(source.canInterfaces);
  const isHomeZero = route === HOME_ZERO_ROUTE;

  return (
    <section className="oa-s02" aria-labelledby="oa-s02-title" data-route={route}>
      <header className="oa-s02__head">
        <p className="oa-s02__id">{isHomeZero ? HOME_ZERO_ROUTE : CONNECTION_ROUTE}</p>
        <h1 id="oa-s02-title" className="oa-s02__title">
          {isHomeZero ? "홈·영점" : "로봇 연결"}
        </h1>
      </header>

      {isHomeZero ? (
        <>
          <ZeroConfirmView
            jointNames={source.jointNames}
            restPositionsRad={source.restPositionsRad}
            currentPositionsRad={source.currentPositionsRad}
            nowMonoMs={source.nowMonoMs}
          />
          <CalibrationView calibration={source.calibration} />
          <RezeroDialog
            side={side ?? "unset"}
            jointNames={source.jointNames}
            restPositionsRad={source.restPositionsRad}
            currentPositionsRad={source.currentPositionsRad}
            nowMonoMs={source.nowMonoMs}
            onComplete={onRezeroAudit}
          />
        </>
      ) : (
        <>
          <SideSelector side={side} onSelect={setSide} />
          <HardwareInventory adapters={source.adapters} />
          <CanDiagnostics interfaces={source.canInterfaces} />
          <FirstConnectWizard discoveredMotors={source.discoveredMotors} />
          <ProfileSelect
            profiles={source.profiles}
            side={side}
            selectedProfile={selectedProfile}
            onSelect={setSelectedProfile}
          />
          <BringupPanel
            side={side}
            canStartupBlocked={canStartupBlocked}
            onAction={onBringupAction}
          />
        </>
      )}
    </section>
  );
}
