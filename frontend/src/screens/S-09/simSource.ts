// The inputs S-09 renders from. Like the viewport, the sim screen is a window:
// the active backend, the real arm's gain profile, the dry-run report, and the
// joint states behind the ghost overlay all originate in the backend. This module
// names that input bundle and supplies an offline default fixture standing in for
// a backend that is not attached — the GUI is verified against fixtures, never real
// hardware (WP-G-S09 is AI-offline).
//
// The default is deliberately honest about its pre-run state: no dry-run report
// (so real-send reads BLOCKED, not "fine"), and the compliant gain profile (so the
// twin/dry-run gate reads REFUSED until the operator sets the real arm to stiff).

import { defaultViewportSource, type ViewportSource } from "../../viewport";
import type {
  ControlTarget,
  DryRunReport,
  GainProfile,
  SimBackend,
} from "./simDomain";
import { DEFAULT_SIM_BACKEND } from "./simDomain";

export interface SimSource {
  // The physics backend the sim is running on (FR-SIM-097).
  readonly backend: SimBackend;
  // The real arm's active PD gain profile (backend state, FR-SIM-028b).
  readonly gainProfile: GainProfile;
  // Which Robot object the operator's commands are pointed at (FR-SIM-097).
  readonly controlTarget: ControlTarget;
  // The most recent backend dry-run report, or null before any dry-run.
  readonly dryRunReport: DryRunReport | null;
  // The viewport input bundle both ghost layers render over.
  readonly viewport: ViewportSource;
}

export function defaultSimSource(): SimSource {
  return {
    backend: DEFAULT_SIM_BACKEND,
    gainProfile: "compliant",
    controlTarget: "sim",
    dryRunReport: null,
    viewport: defaultViewportSource(),
  };
}
