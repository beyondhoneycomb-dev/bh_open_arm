// Named camera view presets. Positions are in Three.js render space (Y-up, metres)
// and all look at the scene origin, so they compose with the ROS->Three world
// frame rather than re-deriving it. Presets are a convenience layer over the
// orbit camera; they carry no robot state and issue no command.

import type { PerspectiveCamera } from "three";

export type ViewPresetId = "front" | "side" | "top" | "iso";

export interface CameraPreset {
  readonly label: string;
  // Camera position in Three.js space; the target is always the origin.
  readonly position: readonly [number, number, number];
}

export const VIEW_PRESETS: Readonly<Record<ViewPresetId, CameraPreset>> = {
  front: { label: "정면", position: [0, 1.1, 2.6] },
  side: { label: "측면", position: [2.6, 1.1, 0] },
  top: { label: "상면", position: [0, 3.2, 0.001] },
  iso: { label: "등각", position: [1.9, 1.7, 1.9] },
};

export const VIEW_PRESET_IDS: readonly ViewPresetId[] = ["front", "side", "top", "iso"];

// Point a camera at the origin from a preset. Kept out of the React component so
// it can be exercised without a WebGL context.
export function applyPreset(camera: PerspectiveCamera, presetId: ViewPresetId): void {
  const [x, y, z] = VIEW_PRESETS[presetId].position;
  camera.position.set(x, y, z);
  camera.lookAt(0, 0, 0);
  camera.updateProjectionMatrix();
}
