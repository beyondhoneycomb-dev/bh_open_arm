// CG-5-04f — command-source exclusivity: no UI state in which more than one command
// source is simultaneously authoritative. A "UI state" is a mode: the mode catalog
// (mode/modes.ts) assigns each mode exactly one send_action holder, so exclusivity is
// structural. This audit reads that catalog as data and fails any mode that lists more
// than one active source. The one screen with two candidate sources (S-05 teleop:
// VR + GUI manual) additionally has to EXPRESS the mutual disable, so a second check
// confirms that expression exists in the teleop subtree.

import type { AuditViolation, ScannedSource } from "./types";

// A mode and the command sources that hold authority in it. "none" holders (IDLE)
// contribute an empty list; every other mode contributes exactly one source.
export interface ModeAuthority {
  mode: string;
  holders: readonly string[];
}

// One mode catalog descriptor as the audit consumes it, matching mode/modes.ts
// ModeDescriptor structurally without importing its exact type.
export interface CatalogMode {
  id: string;
  holder: string;
}

// Project the mode catalog into per-mode authority: the "none" holder means no source
// commands (IDLE), so it maps to an empty list rather than a phantom source.
export function modeAuthoritiesFromCatalog(modes: readonly CatalogMode[]): ModeAuthority[] {
  return modes.map((mode) => ({
    mode: mode.id,
    holders: mode.holder === "none" ? [] : [mode.holder],
  }));
}

// Fail any mode with two or more concurrently authoritative sources.
export function auditCommandSourceExclusivity(
  authorities: readonly ModeAuthority[],
): AuditViolation[] {
  const violations: AuditViolation[] = [];
  for (const authority of authorities) {
    if (authority.holders.length > 1) {
      violations.push({
        check: "CG-5-04f",
        where: authority.mode,
        detail: `mode has ${authority.holders.length} simultaneous command sources: ${authority.holders.join(", ")}`,
      });
    }
  }
  return violations;
}

const SINGLE_ACTIVE_SOURCE = /activeCommandSource/;
const MANUAL_DISABLE = /manualControlDisabled/;

// The teleop screen must resolve a single active command source AND disable the
// alternate, so the two candidate sources can never both command. Returns true when
// both are expressed in the teleop subtree.
export function teleopExpressesExclusivity(sources: readonly ScannedSource[]): boolean {
  const hasSingleActive = sources.some((source) => SINGLE_ACTIVE_SOURCE.test(source.code));
  const hasDisable = sources.some((source) => MANUAL_DISABLE.test(source.code));
  return hasSingleActive && hasDisable;
}
