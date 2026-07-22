// The shared 3D <canvas> component. It owns the WebGL lifecycle: it builds the
// Three.js scene (ROS Z-up -> Three Y-up root), creates the renderer only when a
// WebGL context is actually available, runs the render loop, applies view presets
// and joint snapshots, and disposes on unmount. Where WebGL is unavailable — a
// headless or test environment — it renders an honest, accessible fallback rather
// than throwing, so the surrounding controls stay verifiable without a GPU.
//
// Joint snapshots arrive already validated as full snapshots (CG-G-02d) and in
// radians (CG-G-02a); this component forwards them through the batch, radian path
// and never converts units or calls a degree-valued setter.

import { useEffect, useRef, useState } from "react";
import { Color, WebGLRenderer } from "three";

import { applyJointSnapshot, type JointTarget } from "./scene/applyJoints";
import { buildViewportScene, type ViewportScene } from "./scene/buildScene";
import { applyPreset, type ViewPresetId } from "./scene/viewPresets";

interface ViewportCanvasProps {
  presetId: ViewPresetId;
  // A validated full-joint snapshot in radians, or null before the first frame.
  snapshot: Readonly<Record<string, number>> | null;
  // The loaded URDF robot, or null while none is loaded (no backend in this WP).
  robotHandle: JointTarget | null;
  // Whether the current view is stale; drives the canvas tint and status text.
  stale: boolean;
}

function acquireWebGL(canvas: HTMLCanvasElement): boolean {
  try {
    return Boolean(canvas.getContext("webgl2") ?? canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

export function ViewportCanvas({ presetId, snapshot, robotHandle, stale }: ViewportCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const sceneRef = useRef<ViewportScene | null>(null);
  const [webglAvailable, setWebglAvailable] = useState<boolean>(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !acquireWebGL(canvas)) {
      setWebglAvailable(false);
      return;
    }
    const viewportScene = buildViewportScene(new Color(0x10151b));
    sceneRef.current = viewportScene;
    setWebglAvailable(true);

    const renderer = new WebGLRenderer({ canvas, antialias: true });
    const width = canvas.clientWidth || canvas.width;
    const height = canvas.clientHeight || canvas.height;
    renderer.setSize(width, height, false);
    viewportScene.camera.aspect = height === 0 ? viewportScene.camera.aspect : width / height;
    viewportScene.camera.updateProjectionMatrix();

    let frame = 0;
    const renderLoop = () => {
      renderer.render(viewportScene.scene, viewportScene.camera);
      frame = requestAnimationFrame(renderLoop);
    };
    frame = requestAnimationFrame(renderLoop);

    return () => {
      cancelAnimationFrame(frame);
      renderer.dispose();
      sceneRef.current = null;
    };
  }, []);

  useEffect(() => {
    const viewportScene = sceneRef.current;
    if (viewportScene) {
      applyPreset(viewportScene.camera, presetId);
    }
  }, [presetId]);

  useEffect(() => {
    if (robotHandle && snapshot) {
      applyJointSnapshot(robotHandle, snapshot);
    }
  }, [robotHandle, snapshot]);

  return (
    <div className={`oa-viewport-canvas${stale ? " oa-viewport-canvas--stale" : ""}`}>
      <canvas ref={canvasRef} className="oa-viewport-canvas__gl" />
      {!webglAvailable && (
        <div
          className="oa-viewport-canvas__fallback"
          role="img"
          aria-label="3D 뷰포트 (이 환경에서 WebGL 미가용 — 렌더 생략)"
        >
          <p>3D 뷰 미가용</p>
          <p className="oa-viewport-canvas__fallback-note">
            WebGL 컨텍스트가 없는 환경 — 씬 로직은 활성, 렌더만 생략
          </p>
        </div>
      )}
      {stale && (
        <p className="oa-viewport-canvas__stale-tag" role="status">
          STALE
        </p>
      )}
    </div>
  );
}
