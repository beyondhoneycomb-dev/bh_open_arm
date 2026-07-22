// Tile derivation from the observation-feature keyset (CG-G-S06a, CG-G-S06b).
//
// The tile set is NOT a compiled-in list. It is derived at render time from
// `robot.observation_features`, so adding or removing a camera changes the grid
// with zero code change and no empty/orphan tile (CG-G-S06a). The camera slot
// key is the CTR-PRIM@v1 identifier that round-trips across CAM/CAP/WS/REC, so a
// tile carries BOTH the operator-facing UI label AND the dataset key it maps to
// (`observation.images.<slot>`); the two are never rendered apart (CG-G-S06b).
//
// This is a facade: the derivation reads the backend keyset and the frozen
// CTR-PRIM join forms exported by the WS foundation. It invents no camera and
// re-attaches no arm prefix — the prefix is the backend's `arm_slot` output; the
// screen only splits it back to render a human label.

import {
  DEPTH_KEY_SUFFIX,
  IMAGE_FEATURE_PREFIX,
  isImageFeatureKey,
  type CameraChannel,
} from "../../ws/envelope";

// The CTR-PRIM@v1 per-arm prefixes (primitive 1). The backend AUTO-ATTACHES one
// of these to a base name; the screen splits it back out for the label only. The
// contract test asserts this list equals the frozen prim/schema.json arm_prefixes,
// so a prim bump fails the lane rather than letting the split drift (CR-2).
export const ARM_PREFIXES: ReadonlyArray<readonly [string, string]> = [
  ["left", "left_"],
  ["right", "right_"],
];

export interface CameraTileModel {
  // The CTR-PRIM@v1 slot key — the registered identity, arm prefix included.
  slot: string;
  // The operator-facing label: base name then side, e.g. `left_wrist` → `wrist_left`.
  uiLabel: string;
  // The dataset RGB feature key, always shown beside the label (CG-G-S06b).
  datasetKey: string;
  // The dataset depth feature key when this camera carries depth, else null.
  datasetDepthKey: string | null;
  // Whether the depth channel is present in the feature keyset.
  hasDepth: boolean;
  // The arm this camera is bound to (`left`/`right`), or null for a top-level camera.
  arm: string | null;
}

interface SlotChannel {
  slot: string;
  channel: CameraChannel;
}

// Recover `{slot, channel}` from an `observation.images.*` feature key, mirroring
// the frozen CTR-PRIM join (depth is the `_depth`-suffixed key of the same slot).
// A non-image key returns null so the state vector and action keys are ignored.
export function slotChannelFromFeatureKey(key: string): SlotChannel | null {
  if (!isImageFeatureKey(key)) {
    return null;
  }
  const body = key.slice(IMAGE_FEATURE_PREFIX.length);
  if (body.endsWith(DEPTH_KEY_SUFFIX)) {
    return { slot: body.slice(0, body.length - DEPTH_KEY_SUFFIX.length), channel: "depth" };
  }
  return { slot: body, channel: "rgb" };
}

// Split a slot key into its arm side and bare base name. A top-level camera has
// no arm prefix, so `arm` is null and `base` is the whole slot.
export function splitArm(slot: string): { arm: string | null; base: string } {
  for (const [side, prefix] of ARM_PREFIXES) {
    if (slot.startsWith(prefix)) {
      return { arm: side, base: slot.slice(prefix.length) };
    }
  }
  return { arm: null, base: slot };
}

// The operator-facing label. For a per-arm camera the side moves to the end
// (`left_wrist` → `wrist_left`) so the base reads first; a top-level camera keeps
// its bare slot. The registered dataset key is shown separately, never replaced.
export function uiLabelForSlot(slot: string): string {
  const { arm, base } = splitArm(slot);
  return arm === null ? slot : `${base}_${arm}`;
}

// Derive the ordered tile set from the observation feature keyset. One tile per
// camera slot; a slot's depth channel folds into the same tile as `hasDepth`.
// The returned length IS the tile count — there is no separate count constant.
export function deriveTiles(observationFeatures: readonly string[]): CameraTileModel[] {
  const slots = new Map<string, { hasDepth: boolean }>();
  for (const key of observationFeatures) {
    const parsed = slotChannelFromFeatureKey(key);
    if (parsed === null) {
      continue;
    }
    const entry = slots.get(parsed.slot) ?? { hasDepth: false };
    if (parsed.channel === "depth") {
      entry.hasDepth = true;
    }
    slots.set(parsed.slot, entry);
  }

  return [...slots.entries()]
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .map(([slot, entry]) => {
      const { arm } = splitArm(slot);
      return {
        slot,
        uiLabel: uiLabelForSlot(slot),
        datasetKey: `${IMAGE_FEATURE_PREFIX}${slot}`,
        datasetDepthKey: entry.hasDepth ? `${IMAGE_FEATURE_PREFIX}${slot}${DEPTH_KEY_SUFFIX}` : null,
        hasDepth: entry.hasDepth,
        arm,
      };
    });
}
