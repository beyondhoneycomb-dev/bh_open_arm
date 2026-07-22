// Layer visibility and the Auto/Visual/Collision render modes. A URDF carries two
// geometry sets per link — visual meshes and collision geoms. The three modes
// choose which is drawn:
//
//   - Auto: draw the visual meshes when the link has them, else the collision
//     geom (the ordinary "show me the robot" view);
//   - Visual: force the visual meshes;
//   - Collision: force the collision geoms, and surface any link whose collision
//     geometry is missing (CG-G-02g) rather than drawing a gap as if it were fine.
//
// There is no point-cloud layer: PG-DEPTH-001 accepts an RGB-only reduction, so
// the depth source is gone and the layer with it (see constants). The layer set
// below is deliberately complete — adding a point-cloud toggle would imply a
// source that does not exist.

export type RenderMode = "auto" | "visual" | "collision";

export interface LayerState {
  readonly visualMeshes: boolean;
  readonly collisionGeoms: boolean;
  readonly jointFrames: boolean;
  readonly grid: boolean;
}

export const DEFAULT_LAYER_STATE: LayerState = {
  visualMeshes: true,
  collisionGeoms: false,
  jointFrames: false,
  grid: true,
};

export const RENDER_MODES: readonly RenderMode[] = ["auto", "visual", "collision"];

export const RENDER_MODE_LABELS: Readonly<Record<RenderMode, string>> = {
  auto: "Auto",
  visual: "Visual",
  collision: "Collision",
};

// Which geometry a single link draws under a mode, given what it actually has.
// Auto prefers visual and falls back to collision; the explicit modes force one.
export function meshSelectionFor(
  mode: RenderMode,
  hasVisual: boolean,
  hasCollision: boolean,
): "visual" | "collision" | "none" {
  if (mode === "visual") {
    return hasVisual ? "visual" : "none";
  }
  if (mode === "collision") {
    return hasCollision ? "collision" : "none";
  }
  if (hasVisual) {
    return "visual";
  }
  return hasCollision ? "collision" : "none";
}

// Resolve the effective layer visibility for a mode. Visual/Collision modes pin
// their geometry layer on and the other off so the toggles reflect what is drawn;
// Auto leaves the operator's toggles as they are.
export function layersForMode(mode: RenderMode, base: LayerState): LayerState {
  if (mode === "visual") {
    return { ...base, visualMeshes: true, collisionGeoms: false };
  }
  if (mode === "collision") {
    return { ...base, visualMeshes: false, collisionGeoms: true };
  }
  return base;
}
