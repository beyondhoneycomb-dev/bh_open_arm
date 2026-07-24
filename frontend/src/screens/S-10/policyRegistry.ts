// The runtime-derived policy list (CG-G-S10a / FR-GUI-121). The screen must contain
// ZERO hardcoded policy names: a baked-in list goes silently stale on a lerobot upgrade
// and the FR-OPS-089 contract-regression check cannot catch it (a UI list is not in its
// scope). So every policy name and every dimension ceiling arrives as DATA — here, from
// the captured registry snapshot; in production, from the live WS response the backend
// builds by introspecting the installed config classes (WP-4B-01). This module loads
// that data and never names a policy.
//
// The snapshot is imported as raw text (a `.json` asset, not a `.ts` source), so the
// policy-name strings live in data the static scan does not read — which is the point:
// the code has none, the data has all. `resolvePolicyOptions` is the AI-offline
// stand-in for the WP-4B-01 three-axis matrix; the live source replaces it with the
// backend's decision. It is called only by the fixture (trainingSource.ts), never by a
// view or the screen, so the facade owns no validation truth.

import snapshotText from "./policyRegistrySnapshot.json?raw";
import type { DatasetOption, PolicyCapability, PolicyOption } from "./types";

// The 32-vs-48 dimension block code (mirrors the backend policy_compat block_reason
// code). Only the CODE is named here; the LIMIT is read from the capability's
// source-derived `maxStateDim`, never a constant in this file.
const STATE_DIM_OVER_CAP = "STATE_DIM_OVER_CAP";

interface RawPolicy {
  id: string;
  configClass: string;
  maxStateDim: number | null;
  maxActionDim: number | null;
  capSource: string;
  available: boolean;
  unavailableReason: string | null;
}

interface RawSnapshot {
  lerobotVersion: string;
  policies: RawPolicy[];
}

function parseSnapshot(): RawSnapshot {
  const parsed = JSON.parse(snapshotText) as RawSnapshot;
  if (!Array.isArray(parsed.policies) || parsed.policies.length === 0) {
    throw new Error("policy registry snapshot carries no policies");
  }
  return parsed;
}

// The installed policy capabilities, source-derived, in registry order. The screen and
// the fixture read the list from here; neither writes a policy name.
export function loadPolicyCapabilities(): PolicyCapability[] {
  return parseSnapshot().policies.map((raw) => ({
    id: raw.id,
    configClass: raw.configClass,
    maxStateDim: raw.maxStateDim,
    maxActionDim: raw.maxActionDim,
    capSource: raw.capSource,
    available: raw.available,
    unavailableReason: raw.unavailableReason,
  }));
}

// The lerobot version the snapshot was captured against, for the "runtime-derived"
// provenance line the form shows.
export function snapshotLerobotVersion(): string {
  return parseSnapshot().lerobotVersion;
}

// The AI-offline stand-in for the WP-4B-01 matrix: block a policy whose source-derived
// ceiling is exceeded by the selected dataset's observation width, and carry the SOURCE
// of that ceiling in the reason (CG-G-S10e). A policy the backend marked unavailable
// (vqbet) is blocked with its unavailable reason regardless of dimension (CG-G-S10g).
// The limit comes from the capability, never a literal here — a source-derived cap is
// never copied (the load-bearing invariant of WP-4B-01).
export function resolvePolicyOptions(
  capabilities: readonly PolicyCapability[],
  dataset: DatasetOption,
): PolicyOption[] {
  return capabilities.map((capability) => {
    if (!capability.available) {
      return {
        capability,
        blocked: true,
        blockReason: {
          code: "POLICY_UNAVAILABLE",
          observed: dataset.stateDim,
          limit: capability.maxStateDim ?? dataset.stateDim,
          source: capability.capSource,
          human:
            capability.unavailableReason ??
            `${capability.id} is marked unavailable by the backend registry`,
        },
      };
    }
    const limit = capability.maxStateDim;
    if (limit !== null && dataset.stateDim > limit) {
      return {
        capability,
        blocked: true,
        blockReason: {
          code: STATE_DIM_OVER_CAP,
          observed: dataset.stateDim,
          limit,
          source: capability.capSource,
          human:
            `observation.state width ${dataset.stateDim} exceeds this policy's ` +
            `max_state_dim ceiling ${limit}; drop velocity/torque or pick an uncapped policy`,
        },
      };
    }
    return { capability, blocked: false, blockReason: null };
  });
}
