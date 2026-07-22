import { describe, expect, it } from "vitest";

import { imageFeatureKey } from "../../ws/envelope";
import { deriveTiles, slotChannelFromFeatureKey, splitArm, uiLabelForSlot } from "./tiles";

describe("tile derivation from observation_features (CG-G-S06a)", () => {
  it("derives one tile per camera slot, ignoring non-image features", () => {
    const features = [
      "observation.state",
      "action",
      imageFeatureKey("left_wrist", "rgb"),
      imageFeatureKey("right_wrist", "rgb"),
      imageFeatureKey("right_wrist", "depth"),
      imageFeatureKey("front", "rgb"),
    ];
    const tiles = deriveTiles(features);
    expect(tiles.map((tile) => tile.slot)).toEqual(["front", "left_wrist", "right_wrist"]);
    expect(tiles.find((tile) => tile.slot === "right_wrist")?.hasDepth).toBe(true);
    expect(tiles.find((tile) => tile.slot === "left_wrist")?.hasDepth).toBe(false);
  });

  it("follows a camera add and remove with no fixed count", () => {
    const base = [imageFeatureKey("front", "rgb"), imageFeatureKey("left_wrist", "rgb")];
    expect(deriveTiles(base)).toHaveLength(2);

    const added = [...base, imageFeatureKey("overhead", "rgb")];
    expect(deriveTiles(added)).toHaveLength(3);

    const removed = base.filter((key) => key !== imageFeatureKey("front", "rgb"));
    expect(deriveTiles(removed)).toHaveLength(1);
  });

  it("emits an empty tile set when no camera key is present", () => {
    expect(deriveTiles(["observation.state", "action"])).toEqual([]);
  });
});

describe("UI label and dataset key both derived (CG-G-S06b)", () => {
  it("shows the reordered UI label and the registered dataset key", () => {
    const tiles = deriveTiles([imageFeatureKey("left_wrist", "rgb")]);
    expect(tiles[0].uiLabel).toBe("wrist_left");
    expect(tiles[0].datasetKey).toBe("observation.images.left_wrist");
    expect(tiles[0].arm).toBe("left");
  });

  it("keeps a top-level camera's bare slot as its label", () => {
    expect(uiLabelForSlot("front")).toBe("front");
    expect(splitArm("front")).toEqual({ arm: null, base: "front" });
  });

  it("derives the depth dataset key only for a depth camera", () => {
    const tiles = deriveTiles([
      imageFeatureKey("right_wrist", "rgb"),
      imageFeatureKey("right_wrist", "depth"),
    ]);
    expect(tiles[0].datasetDepthKey).toBe("observation.images.right_wrist_depth");
    const rgbOnly = deriveTiles([imageFeatureKey("front", "rgb")]);
    expect(rgbOnly[0].datasetDepthKey).toBeNull();
  });
});

describe("feature-key parsing mirrors the CTR-PRIM join", () => {
  it("splits rgb and depth channels back to the same slot", () => {
    expect(slotChannelFromFeatureKey("observation.images.front")).toEqual({
      slot: "front",
      channel: "rgb",
    });
    expect(slotChannelFromFeatureKey("observation.images.front_depth")).toEqual({
      slot: "front",
      channel: "depth",
    });
    expect(slotChannelFromFeatureKey("observation.state")).toBeNull();
  });
});
