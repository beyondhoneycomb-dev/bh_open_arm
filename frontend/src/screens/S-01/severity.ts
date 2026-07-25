// Presentation ORDERING for the dashboard — not computation. The dashboard packs
// nine subsystems and a dozen metrics onto one screen (FR-GUI-100), which is "the
// shortcut that makes the most important thing least visible" (02c §4.2 tradeoff). The
// mitigation is a severity-sorted layout plus a CRITICAL-only area. Everything
// here reorders and buckets values the backend already decided; it reads no metric
// and decides no threshold (CG-G-S01a), so there is no arithmetic and no numeric
// comparison in this file — only a fixed order table and set membership.

import { UNAVAILABLE } from "./types";
import type { SubsystemRenderState, SubsystemStatus } from "./types";

// Attention order, most-urgent first. ERROR and STALE outrank WARN. UNAVAILABLE
// ("we cannot confirm this subsystem") ranks ABOVE OK on purpose: a gap must
// never sit quietly among the greens (CG-G-S01e). OK is last.
export const SEVERITY_DISPLAY_ORDER: readonly SubsystemRenderState[] = [
  "ERROR",
  "STALE",
  "WARN",
  UNAVAILABLE,
  "OK",
];

// The render-state of a subsystem: its diagnostic status, or UNAVAILABLE when the
// producing backend has not landed (status null). This is the one place the
// not-landed -> UNAVAILABLE resolution lives, and it never resolves to OK — the
// whole point of CG-G-S01e. A `??` here is presence handling, not a threshold.
export function subsystemRenderState(subsystem: SubsystemStatus): SubsystemRenderState {
  return subsystem.status ?? UNAVAILABLE;
}

// The nine subsystems reordered by attention. Stable within a bucket (the input
// order is the 14 §4.3 canon order), so a row's neighbours only change when its
// state changes — the layout-moves-with-state cost the mitigation accepts.
export function bySeverity(
  subsystems: readonly SubsystemStatus[],
): SubsystemStatus[] {
  return SEVERITY_DISPLAY_ORDER.flatMap((state) =>
    subsystems.filter((subsystem) => subsystemRenderState(subsystem) === state),
  );
}

// The subsystems the backend marked CRITICAL — the CRITICAL-only area's contents.
// Membership is the backend's `critical` flag; the dashboard decides none of it.
export function criticalSubsystems(
  subsystems: readonly SubsystemStatus[],
): SubsystemStatus[] {
  return subsystems.filter((subsystem) => subsystem.critical);
}

// The CSS state class for a render-state, by table lookup (no comparison). The
// UNAVAILABLE class is deliberately distinct from the OK class so a gap never
// reads as green.
export const RENDER_STATE_CLASS: Readonly<Record<SubsystemRenderState, string>> = {
  OK: "oa-dash__state--ok",
  WARN: "oa-dash__state--warn",
  ERROR: "oa-dash__state--error",
  STALE: "oa-dash__state--stale",
  [UNAVAILABLE]: "oa-dash__state--unavailable",
};

// The operator-facing label for a render-state, by table lookup. UNAVAILABLE is
// labelled as such — never blank, never "OK".
export const RENDER_STATE_LABEL: Readonly<Record<SubsystemRenderState, string>> = {
  OK: "OK",
  WARN: "WARN",
  ERROR: "ERROR",
  STALE: "STALE",
  [UNAVAILABLE]: "미가용 (UNAVAILABLE)",
};
