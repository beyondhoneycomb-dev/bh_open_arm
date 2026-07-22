// Render-mode geometry selection and layer resolution, plus the standing fact that
// the point-cloud layer is gone (PG-DEPTH-001 RGB-only reduction, WP-G-02 branch).

import { describe, expect, it } from "vitest";

import { POINTCLOUD_LAYER_AVAILABLE, POINTCLOUD_REDUCTION_NOTICE } from "../constants";
import {
  DEFAULT_LAYER_STATE,
  layersForMode,
  meshSelectionFor,
  RENDER_MODES,
} from "./layers";

describe("render-mode geometry selection", () => {
  it("Auto prefers visual and falls back to collision", () => {
    expect(meshSelectionFor("auto", true, true)).toBe("visual");
    expect(meshSelectionFor("auto", false, true)).toBe("collision");
    expect(meshSelectionFor("auto", false, false)).toBe("none");
  });

  it("Visual and Collision force their own geometry", () => {
    expect(meshSelectionFor("visual", true, true)).toBe("visual");
    expect(meshSelectionFor("visual", false, true)).toBe("none");
    expect(meshSelectionFor("collision", true, true)).toBe("collision");
    expect(meshSelectionFor("collision", true, false)).toBe("none");
  });

  it("offers exactly the three modes", () => {
    expect(RENDER_MODES).toEqual(["auto", "visual", "collision"]);
  });

  it("pins geometry layers per mode", () => {
    const collision = layersForMode("collision", DEFAULT_LAYER_STATE);
    expect(collision.collisionGeoms).toBe(true);
    expect(collision.visualMeshes).toBe(false);
    const visual = layersForMode("visual", DEFAULT_LAYER_STATE);
    expect(visual.visualMeshes).toBe(true);
    expect(visual.collisionGeoms).toBe(false);
  });
});

describe("point-cloud layer removed (PG-DEPTH-001 reduction)", () => {
  it("declares no point-cloud layer in the layer state", () => {
    expect(Object.keys(DEFAULT_LAYER_STATE)).toEqual([
      "visualMeshes",
      "collisionGeoms",
      "jointFrames",
      "grid",
    ]);
    expect(POINTCLOUD_LAYER_AVAILABLE).toBe(false);
    expect(POINTCLOUD_REDUCTION_NOTICE.length).toBeGreaterThan(0);
  });
});
