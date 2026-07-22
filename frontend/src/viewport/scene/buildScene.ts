// Pure Three.js scene assembly, with no renderer and no DOM. The renderer needs a
// WebGL context (a browser concern owned by ViewportCanvas); everything here is
// plain scene-graph maths that runs anywhere, so the world-frame orientation and
// the camera can be verified without a GPU. The URDF robot, once loaded, is added
// under `root`, which carries the ROS->Three world frame so the robot renders
// upright (CG-G-02c).

import {
  AmbientLight,
  Color,
  DirectionalLight,
  GridHelper,
  Group,
  PerspectiveCamera,
  Scene,
} from "three";

import { applyWorldFrame } from "./coordinateTransform";
import { applyPreset } from "./viewPresets";

export interface ViewportScene {
  readonly scene: Scene;
  // The ROS-frame root: URDF content is added here so it inherits the Z-up->Y-up
  // rotation. Render-frame decorations (grid, lights) live on the scene directly.
  readonly root: Group;
  readonly camera: PerspectiveCamera;
}

// Three.js PerspectiveCamera vertical field of view. Three's camera API takes fov
// in its own render-space units; this is a lens parameter, not a robot quantity.
const CAMERA_FOV = 50;
const CAMERA_NEAR_M = 0.01;
const CAMERA_FAR_M = 100;
const GRID_SIZE_M = 4;
const GRID_DIVISIONS = 16;
const DEFAULT_ASPECT = 16 / 9;

// Assemble the scene graph. `background` is a Three.js color the caller may theme;
// the default is a neutral dark that reads in both light and dark shells.
export function buildViewportScene(background: Color = new Color(0x10151b)): ViewportScene {
  const scene = new Scene();
  scene.background = background;

  const root = new Group();
  root.name = "ros-root";
  applyWorldFrame(root);
  scene.add(root);

  const grid = new GridHelper(GRID_SIZE_M, GRID_DIVISIONS);
  grid.name = "floor-grid";
  scene.add(grid);

  const ambient = new AmbientLight(0xffffff, 0.6);
  scene.add(ambient);
  const key = new DirectionalLight(0xffffff, 0.8);
  key.position.set(2, 4, 3);
  scene.add(key);

  const camera = new PerspectiveCamera(CAMERA_FOV, DEFAULT_ASPECT, CAMERA_NEAR_M, CAMERA_FAR_M);
  applyPreset(camera, "iso");

  return { scene, root, camera };
}
