// The public (unauthenticated) health projection — CG-5-02c / FR-OPS-027 revision.
// The read-only health endpoint returns every subsystem state and active error
// code with no side effects, but its UNAUTHENTICATED response must NOT expose the
// current control-holder or the active-profile id: those leak operational
// information from a public endpoint. The authenticated operator console (this
// dashboard) may show them; the public projection strips them.
//
// This module mirrors that redaction as a TS shape and a pure projection so the
// boundary is testable in the frontend lane: `PublicHealth` STRUCTURALLY has no
// holder/profile field, and `toPublicHealth` carries none across. The real
// endpoint is the backend's (WP-OPS-05 / FR-OPS-027); this is the render/mirror
// side of the same contract, so a regression that reintroduced the fields would
// fail here (health.test.ts) as well as at the server.

import type { DashboardData, DiagnosticState, SubsystemId } from "./types";

// One subsystem as the PUBLIC health response carries it: identity and state
// only. No holder, no profile — those are not part of this shape at all, so they
// cannot leak through it.
export interface PublicHealthSubsystem {
  id: SubsystemId;
  label: string;
  status: DiagnosticState | null;
  critical: boolean;
}

// The whole PUBLIC health response. Deliberately has NO `controlHolder`, NO
// `activeProfileId`, NO `sessionId` — the unauthenticated caller sees subsystem
// health and active error codes, nothing that names who holds control or what
// profile is loaded (FR-OPS-027).
export interface PublicHealth {
  connected: boolean;
  mode: string;
  subsystems: PublicHealthSubsystem[];
  activeErrorCodes: string[];
}

// Project the authenticated dashboard snapshot down to the public health shape,
// dropping the control-holder and active-profile id. Built field by field (never
// a spread of the connection object) so a new sensitive field added upstream is
// omitted by default rather than copied through by accident.
export function toPublicHealth(data: DashboardData): PublicHealth {
  return {
    connected: data.connection.connected,
    mode: data.connection.mode,
    subsystems: data.subsystems.map((subsystem) => ({
      id: subsystem.id,
      label: subsystem.label,
      status: subsystem.status,
      critical: subsystem.critical,
    })),
    activeErrorCodes: [...data.activeErrorCodes],
  };
}
