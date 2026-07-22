// The consume-the-frozen-contract proof for S-06. The screen derives tiles and
// labels from the CTR-PRIM@v1 camera-identifier join and mirrors the five
// hand-eye method names and the depth no-measurement sentinel. This test reads
// the frozen contract bodies (contracts/prim/schema.json, contracts/camera_registry/
// schema.json) and the backend calibration/depth constants and asserts the
// browser mirror equals them — so a contract bump fails the lane (CR-2 staleness)
// rather than letting the screen drift.

import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { imageFeatureKey } from "../../ws/envelope";
import { ARM_PREFIXES, deriveTiles } from "./tiles";
import { HAND_EYE_METHOD_NAMES } from "./handEye";
import { DEPTH_NO_MEASUREMENT_MM } from "./depthColormap";

function findRepoRoot(): string {
  let dir = dirname(fileURLToPath(import.meta.url));
  for (let depth = 0; depth < 12; depth += 1) {
    if (existsSync(join(dir, "contracts")) && existsSync(join(dir, "frontend"))) {
      return dir;
    }
    const parent = resolve(dir, "..");
    if (parent === dir) {
      break;
    }
    dir = parent;
  }
  throw new Error("could not locate repository root");
}

const REPO_ROOT = findRepoRoot();

function readJson(relativePath: string): Record<string, unknown> {
  return JSON.parse(readFileSync(join(REPO_ROOT, relativePath), "utf-8"));
}

function readText(relativePath: string): string {
  return readFileSync(join(REPO_ROOT, relativePath), "utf-8");
}

describe("CTR-PRIM@v1 camera-identifier join (CG-G-S06a/b)", () => {
  const prim = readJson("contracts/prim/schema.json");
  const primitives = prim.primitives as Record<string, Record<string, unknown>>;
  const camera = primitives.camera_identifier;

  it("mirrors the frozen arm prefixes", () => {
    const frozen = camera.arm_prefixes as Record<string, string>;
    const mirror = Object.fromEntries(ARM_PREFIXES);
    expect(mirror).toEqual(frozen);
  });

  it("derives the dataset keys from the frozen join forms", () => {
    const joins = camera.joins as Record<string, string>;
    expect(joins.rec_image_key).toBe("observation.images.<slot>");
    expect(joins.rec_depth_key).toBe("observation.images.<slot>_depth");

    const tiles = deriveTiles([
      imageFeatureKey("right_wrist", "rgb"),
      imageFeatureKey("right_wrist", "depth"),
    ]);
    expect(tiles[0].datasetKey).toBe(joins.rec_image_key.replace("<slot>", "right_wrist"));
    expect(tiles[0].datasetDepthKey).toBe(
      joins.rec_depth_key.replace("<slot>", "right_wrist"),
    );
  });

  it("round-trips the derivation with the foundation imageFeatureKey", () => {
    const tiles = deriveTiles([imageFeatureKey("front", "rgb")]);
    expect(tiles[0].datasetKey).toBe(imageFeatureKey("front", "rgb"));
  });

  it("agrees with CTR-CAM@v1 dataset-key derivation and arm-prefix auto-attach", () => {
    const cam = readJson("contracts/camera_registry/schema.json");
    const datasetKeys = cam.dataset_keys as Record<string, string>;
    expect(datasetKeys.rgb).toBe("observation.images.<slot>");
    expect(datasetKeys.depth).toBe("observation.images.<slot>_depth");
    const registration = cam.registration as Record<string, unknown>;
    expect(registration.arm_prefix_auto_attached).toBe(true);
  });
});

describe("CTR-PRIM@v1 frame types and depth sentinel (CG-G-S06d)", () => {
  const prim = readJson("contracts/prim/schema.json");
  const primitives = prim.primitives as Record<string, Record<string, unknown>>;
  const frame = primitives.frame_type;

  it("mirrors the frozen frame types and depth dtype", () => {
    expect(frame.types).toEqual(["rgb", "depth"]);
    expect(frame.required).toBe("rgb");
    expect((frame.dtype as Record<string, string>).depth).toBe("uint16");
  });

  it("mirrors the backend depth no-measurement sentinel", () => {
    const depthConstants = readText("backend/sensing/depth/constants.py");
    const match = /DEPTH_NO_MEASUREMENT_MM\s*=\s*(\d+)/.exec(depthConstants);
    expect(match).not.toBeNull();
    expect(Number(match![1])).toBe(DEPTH_NO_MEASUREMENT_MM);
  });
});

describe("hand-eye five-method names mirror the backend (CG-G-S06f)", () => {
  it("equals HAND_EYE_METHOD_NAMES in the backend calibration constants", () => {
    const constants = readText("backend/sensing/calibration/constants.py");
    const match = /HAND_EYE_METHOD_NAMES\s*=\s*\(([^)]*)\)/.exec(constants);
    expect(match).not.toBeNull();
    const backendNames = [...match![1].matchAll(/"([A-Z]+)"/g)].map((m) => m[1]);
    expect(backendNames).toEqual([...HAND_EYE_METHOD_NAMES]);
  });
});
